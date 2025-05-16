import os
from pathlib import Path
from rocrate.rocrate import ROCrate
from rocrate.model.person import Person
from rocrate.model.data_entity import DataEntity
from rocrate.model.contextentity import ContextEntity
from git import Repo
from git.exc import InvalidGitRepositoryError, GitCommandError
import json
import argparse
import datetime
import nbformat
import sys
import requests
from bs4 import BeautifulSoup
from github import Github
import re
import arrow

LICENCES = json.loads(Path("scripts", "licences.json").read_text())
CONTEXT_PROPERTIES = [
    "author",
    "action",
    "workExample",
    "mainEntityOfPage",
    "subjectOf",
    "isPartOf",
    "license",
]


def main(defaults, version):
    # Make working directory the parent of the scripts directory
    os.chdir(Path(__file__).resolve().parent.parent)
    # Get a list of paths to notebooks in the cwd
    notebooks = get_notebooks()
    # Update the crate
    update_crate(defaults, notebooks, version)


def listify(value):
    if not isinstance(value, list):
        return [value]
    return value


def delistify(value):
    if isinstance(value, list) and len(set(value)) == 1:
        return value[0]
    else:
        return value


def id_ify(elements):
    """Wraps elements in a list with @id keys
    eg, convert ['a', 'b'] to [{'@id': 'a'}, {'@id': 'b'}]
    """
    # If the input is a string, make it a list
    # elements = [elements] if isinstance(elements, str) else elements
    # Nope - single elements shouldn't be lists, see: https://www.researchobject.org/ro-crate/1.1/appendix/jsonld.html
    if isinstance(elements, str):
        return {"@id": elements}
    elif isinstance(elements, list):
        try:
            return [{"@id": e.id} for e in elements]
        except AttributeError:
            return [{"@id": element} for element in elements]


def get_notebooks():
    """Returns a list of paths to jupyter notebooks in the given directory

    Parameters:
        dir: The path to the directory in which to search.

    Returns:
        Paths of the notebooks found in the directory
    """
    files = Path(".").glob("*.ipynb")
    is_notebook = lambda file: not file.name.lower().startswith(
        ("draft", "untitled", "index")
    )
    return list(filter(is_notebook, files))


def update_properties(crate, entry, updates, exclude=[]):
    for key, value in updates.items():
        if key in CONTEXT_PROPERTIES:
            add_entities(crate, entry, key, listify(value))
        elif not key.startswith("@") and key not in exclude:
            entry[key] = value
    return entry


def add_people(crate, authors):
    """Converts a list of authors to a list of Persons to be embedded within an ROCrate

    Parameters:
        crate: The rocrate in which the authors will be created.
        authors:
            A list of author information.
            Expects a dict with at least a 'name' value ('Surname, Givenname')
            If there's an 'orcid' this will be used as the id (and converted to a uri if necessary)
    Returns:
        A list of Persons.
    """
    added = []
    # Loop through list of authors
    for author_data in authors:
        # If there's no orcid, create an id from the name
        if not author_data.get("orcid"):
            author_id = f"#{author_data['name'].replace(', ', '_')}"

        # If there's an orcid but it's not a url, turn it into one
        elif not author_data["orcid"].startswith("http"):
            author_id = f"https://orcid.org/{author_data['orcid']}"

        # Otherwise we'll just use the orcid as the id
        else:
            author_id = author_data["orcid"]
        # Check to see if there's already an entry for this person in the crate
        author = crate.get(author_id)

        # If there's already an entry we'll update the existing properties
        if not author:
            props = {"name": author_data["name"]}
            author = crate.add(Person(crate, author_id, properties=props))
        added.append(update_properties(crate, author, author_data, exclude=["orcid"]))
    return added


def add_update_action(crate, version):
    """
    Adds an UpdateAction to the crate when the repo version is updated.
    """
    # Create an id for the action using the version number
    action_id = f"create_version_{version.replace('.', '_')}"

    # Set basic properties for action
    properties = {
        "@type": "UpdateAction",
        "endDate": datetime.datetime.now().strftime("%Y-%m-%d"),
        "name": f"Create version {version}",
        "actionStatus": {"@id": "http://schema.org/CompletedActionStatus"},
    }

    # Create entity
    crate.add(ContextEntity(crate, action_id, properties=properties))


def add_context_entity(crate, entity):
    """
    Adds a ContextEntity to the crate.

    Parameters:
        crate: the current ROCrate
        entity: A JSONLD ready dict containing "@id" and "@type" values
    """
    return crate.add(ContextEntity(crate, entity["@id"], properties=entity))


def add_page(crate, page_data):
    """
    Create a context entity for a HTML page or resource
    """
    # If it's a url string, convert to a dict
    if isinstance(page_data, str):
        page_data = {"url": page_data}
    page_id = page_data["url"]
    # Check if there's already an entity for this page
    page = crate.get(page_id)
    # If there's not an existing page entity, create one
    if not page:
        # Default properties, might be overwritten by values from page_data
        props = {
            "@id": page_id,
            "@type": page_data.get("@type", "CreativeWork"),
            "url": page_data["url"],
        }
        # Create a new context entity for the page
        page = add_context_entity(crate, props)
    # Update the context entity with additional properties from page data
    page = update_properties(crate, page, page_data)
    # If there's a specific name in an existing record we want to keep it.
    # Otherwise add a default name from the page title
    default_name = get_page_title(page_data["url"])
    if "name" in page_data and page.get("name") == default_name:
        page["name"] = page_data["name"]
    elif not page.get("name"):
        page["name"] = default_name
    return page


def add_pages(crate, pages):
    """
    Add related pages
    """
    added = []
    for page in pages:
        if page:
            added.append(add_page(crate, page))
    return added


def add_licence(crate, licences):
    added = []
    for licence in licences:
        added.append(add_context_entity(crate, LICENCES[licence]))
    return added


def add_entities(crate, record, entity_type, entities):
    if entity_type == "author":
        added = add_people(crate, entities)
    elif entity_type == "action":
        added = add_actions(crate, record, entities)
    elif entity_type == "license":
        added = add_licence(crate, entities)
    else:
        added = add_pages(crate, entities)
    if added and entity_type != "action":
        record[entity_type] = delistify(added)


def get_local_file_stats(local_path):
    stats = {}
    local_file = Path(local_path)
    if local_file.is_dir():
        stats["size"] = len(list(local_file.glob("*")))
        file_stats = local_file.stat()
        stats["dateModified"] = arrow.get(file_stats.st_mtime).isoformat()
    else:
        # Get file stats from local filesystem
        file_stats = local_file.stat()
        stats["contentSize"] = file_stats.st_size
        stats["dateModified"] = arrow.get(file_stats.st_mtime).isoformat()
        if local_file.name.endswith((".csv", ".ndjson")):
            stats["size"] = 0
            with local_file.open("r") as df:
                for line in df:
                    stats["size"] += 1
        stats["sdDatePublished"] = arrow.utcnow().isoformat()
    return stats


def get_gh_parts(url):
    try:
        owner, repo = re.search(
            r"https*://.*(?:github|githubusercontent).com/(.+?)/(.+?)/", url
        ).groups()
    except AttributeError:
        owner = None
        repo = None
    return owner, repo


def get_gh_repo(url):
    owner, repo = get_gh_parts(url)
    if owner and repo:
        g = Github()
        return g.get_repo(f"{owner}/{repo}")


def get_web_file_stats(url):
    stats = {"sdDatePublished": arrow.utcnow().isoformat()}
    if "github" in url:
        repo = get_gh_repo(url)
        file_path = url.split(f"/{repo.default_branch}/")[-1]
        contents = repo.get_contents(file_path)
        stats["size"] = contents.size
        stats["dateModified"] = contents.last_modified_datetime.isoformat()
    else:
        response = requests.head(url)
        stats["size"] = response.headers.get("Content-length")
        stats["dateModified"] = arrow.get(
            response.headers.get("Last-Modified"), "ddd, D MMM YYYY HH:mm:ss ZZZ"
        ).isoformat()
    return stats


def get_repo_link(entry):
    """
    Files and notebooks are usually part of a code repository.
    Also crate can have a codeRepository prop.
    If the files have urls then use the url to get repo.
    Otherwise use the local git info to get repo url.
    """
    repo_url = None
    if url := entry.get("url"):
        owner, repo = get_gh_parts(url)
        if owner and repo:
            repo_url = f"https://github.com/{owner}/{repo}"
    else:
        _, repo_url = get_repo_info()
    return repo_url


def add_repo_link(entry):
    if "isPartOf" not in entry:
        repo_link = get_repo_link(entry)
        if repo_link:
            entry["isPartOf"] = repo_link
    return entry


def add_files(crate, action, files):
    added = []
    for data_file in files:
        local_path = data_file.get("localPath")
        url = data_file.get("url")
        if url or local_path:
            props = {"@type": ["File", "Dataset"]}
            data_file = add_repo_link(data_file)
            if url:
                props["name"] = data_file.get("name", os.path.basename(url))
                if local_path:
                    props.update(get_local_file_stats(local_path))
                else:
                    props.update(get_web_file_stats(url))
                file_added = crate.add_file(url, properties=props)
            elif local_path:
                props["name"] = data_file.get("name", os.path.basename(local_path))
                props.update(get_local_file_stats(local_path))
                file_added = crate.add_file(
                    local_path, properties=props, dest_path=local_path
                )
            file_added = update_properties(
                crate, file_added, data_file, exclude=["localPath"]
            )
            added.append(file_added)
    return added


def add_actions(crate, notebook, actions):
    added = []
    for index, action_data in enumerate(actions):
        action_id = (
            f"#{os.path.basename(notebook.id).replace('.ipynb', '')}_run_{index}"
        )
        props = {
            "@id": action_id,
            "@type": "CreateAction",
            "instrument": id_ify(notebook.id),
            "actionStatus": {"@id": "http://schema.org/CompletedActionStatus"},
            "name": f"Run of notebook: {os.path.basename(notebook.id)}",
        }
        file_dates = []
        for file_relation in ["result", "object"]:
            added_files = add_files(
                crate, action_data, listify(action_data.get(file_relation, []))
            )
            if added_files:
                props[file_relation] = delistify(added_files)
                for data_file in added_files:
                    file_dates.append(data_file.get("dateModified"))
        props["endDate"] = sorted(file_dates)[-1]
        action = add_context_entity(crate, props)
        action = update_properties(
            crate, action, action_data, exclude=["result", "object"]
        )
        crate.root_dataset.append_to("mentions", action)
        added.append(action)
    return added


def add_python_version(crate):
    # Get the version components from the system
    major, minor, micro = sys.version_info[0:3]
    # Construct url and version name
    url = f"https://www.python.org/downloads/release/python-{major}{minor}{micro}/"
    version = f"{major}.{minor}.{micro}"
    # Define properties of context entity
    entity = {
        "@id": url,
        "version": version,
        "name": f"Python {version}",
        "url": url,
        "@type": ["ComputerLanguage", "SoftwareApplication"],
    }
    return crate.add(ContextEntity(crate, entity["@id"], properties=entity))


def get_page_title(url):
    """
    Get title of the page at the supplied url.
    """
    response = requests.get(url)
    if response.ok:
        soup = BeautifulSoup(response.text, features="lxml")
        return soup.title.string.strip()


def get_repo_info():
    # Try to get some info from the local git repo
    try:
        repo = Repo(".")
        repo_url = repo.git.config("--get", "remote.origin.url").replace(".git", "/")
        repo_name = repo_url.strip("/").split("/")[-1]
    # There is no git repo or no remote set
    except (InvalidGitRepositoryError, GitCommandError):
        repo_url = ""
        repo_name = "example-repo"
    return repo_name, repo_url


def get_nb_metadata(notebook):
    nb = nbformat.read(notebook, nbformat.NO_CONVERT)
    return {k: v for k, v in nb.metadata.rocrate.items() if v}


def add_notebook(crate, notebook):
    # Get metadata embedded in notebooks
    nb_metadata = get_nb_metadata(notebook)
    nb_metadata = add_repo_link(nb_metadata)
    # Default notebook properties
    nb_props = {
        "@type": ["File", "SoftwareSourceCode"],
        "encodingFormat": "application/x-ipynb+json",
        "programmingLanguage": id_ify(add_python_version(crate).id),
        "conformsTo": id_ify("https://purl.archive.org/textcommons/profile#Notebook"),
    }
    # Add notebook to crate
    new_nb = crate.add_file(notebook, properties=nb_props)
    # Add properties from notebook metadata
    new_nb = update_properties(crate, new_nb, nb_metadata)
    return new_nb


def update_crate(defaults, notebooks, version):
    # Load data from an existing crate
    try:
        old_crate = ROCrate(source="./")
        old_root = old_crate.get("./")
        # Get the old root properties
        old_props = old_root.properties()
        # Add old properties to new record (except for those that will be populated from notebooks)
        exclude_keys = ["author", "datePublished", "hasPart", "mentions"]
        root_props = {
            k: v
            for k, v in old_props.items()
            if not (k in exclude_keys or k.startswith("@"))
        }
        # Get version UpdateAction records for inclusion in new crate
        versions = old_crate.get_by_type("UpdateAction")
    # If there's not an existing crate, try to set some default properties
    except (ValueError, FileNotFoundError):
        # Get info from git
        repo_name, repo_url = get_repo_info()
        root_props = {
            "name": defaults.get("name", repo_name),
            "description": defaults.get("description", ""),
            "codeRepository": defaults.get("codeRepository", repo_url),
        }
        versions = []
    # Create a new crate
    crate = ROCrate()
    # Add properties to the root
    root = crate.get("./")
    # update_jsonld doesn't seem to work here?
    for p, v in root_props.items():
        root[p] = v
    # Add version information
    for v in versions:
        crate.add(v)
    # Add authors from defaults
    add_entities(crate, root, "author", defaults.get("authors", []))
    # If this is a new version, change version number and add UpdateAction
    if version:
        root["version"] = version
        add_update_action(crate, version)
    # Add notebooks
    for notebook in notebooks:
        nb = add_notebook(crate, notebook)
        for author in listify(nb.get("author")):
            if author not in root.get("author", []):
                root.append_to("author", author)
    # Set licence of crate metadata
    root["license"] = add_context_entity(crate, LICENCES["metadata"])
    # Save crate
    crate.write("./")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--defaults",
        type=str,
        help="File containing Crate default values",
        required=False,
    )
    parser.add_argument(
        "--version", type=str, help="New version number", required=False
    )
    args = parser.parse_args()
    if args.defaults:
        defaults = json.loads(Path(args.defaults).read_text())
    else:
        defaults = {}

    main(defaults, args.version)
