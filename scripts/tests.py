from update_crate import *
import pytest
from rocrate.rocrate import ROCrate, ContextEntity
from nbformat import NotebookNode
import nbformat
from pathlib import Path
import json
from git import Repo
import pandas as pd
import shutil
import datetime

CONTEXT_PROPERTIES = [
    "author",
    "action",
    "workExample",
    "mainEntityOfPage",
    "subjectOf",
    "isBasedOn",
    "distribution",
    "isPartOf",
    "license",
]

# Utilities


def test_listify_string():
    assert listify("a") == ["a"]


def test_listify_list():
    assert listify(["a"]) == ["a"]


def test_delistify_string():
    assert delistify("a") == "a"


def test_delistify_list_single():
    assert delistify(["a"]) == "a"


def test_delistify_list_multiple():
    assert delistify(["a", "b"]) == ["a", "b"]


@pytest.fixture
def crate():
    crate = CrateMaker()
    crate.crate = ROCrate()
    return crate


@pytest.fixture
def crate_path(tmp_path_factory, crate):
    root = crate.crate.get("./")
    root["name"] = "My ROCrate"
    root["mainEntityOfPage"] = {"@id": "https://glam-workbench.net/trove-newspapers/"}
    crate.add_update_action("v.1.0")
    crate.crate.add_jsonld(
        {
            "@id": "https://glam-workbench.net/trove-newspapers/",
            "@type": "CreativeWork",
            "name": "Trove Newspapers - GLAM-Workbench",
            "url": "https://glam-workbench.net/trove-newspapers/",
        }
    )
    crate_dir = tmp_path_factory.mktemp("crate")
    crate.crate.write(crate_dir)
    return crate_dir


@pytest.fixture
def nb_path(tmp_path_factory):
    nb = nbformat.reads(
        json.dumps(
            {
                "metadata": {
                    "rocrate": {
                        "name": "My test notebook",
                        "description": "This is an example of a notebook for testing.",
                    }
                },
                "cells": [],
            }
        ),
        as_version=nbformat.NO_CONVERT,
    )
    nb_path = tmp_path_factory.mktemp("nbs")
    nbformat.write(nb, Path(nb_path, "test_nb.ipynb"))
    return nb_path


class PageResponse:
    text = (
        "<html><head><title>An interesting web page</title></head><body></body></html>"
    )
    ok = True


class GitHubRepo:
    def __init__(self, *args, **kwargs):
        owner, repo_name = kwargs["full_name_or_id"].split("/")
        self.name = repo_name
        self.owner = owner
        self.default_branch = "master"

    def get_contents(self, *args, **kwargs):
        contents = GenericClass()
        contents.size = 23000
        contents.last_modified_datetime = datetime.datetime(2024, 11, 2)
        return contents


class GenericClass:
    pass


class GitRepo:
    remotes = GenericClass()
    remotes.origin = GenericClass()
    remotes.origin.url = "https://github.com/GLAM-Workbench/recordsearch.git"


@pytest.fixture
def data_file():
    data = [
        {"name": "Bob", "animal": "cat", "number": 3},
        {"name": "Bob", "animal": "dog", "number": 1},
        {"name": "Jan", "animal": "cat", "number": 0},
        {"name": "Jan", "animal": "dog", "number": 2},
    ]
    return pd.DataFrame(data)


class PageHead:
    headers = {
        "Content-length": 23000,
        "Last-Modified": "Fri, 13 Sep 2024 07:01:28 GMT",
    }


@pytest.fixture
def action_data():
    data = {
        "result": [
            {
                "url": "https://github.com/GLAM-Workbench/trove-newspapers-non-english/blob/main/newspapers_non_english.csv"
            }
        ]
    }
    return data


@pytest.fixture
def notebook():
    notebook = GenericClass()
    notebook.id = "test_notebook.ipynb"
    return notebook


def test_id_ify(crate):
    assert crate.id_ify(["a", "b"]) == [{"@id": "a"}, {"@id": "b"}]


def test_get_notebooks(crate, nb_path):
    nbs = crate.get_notebooks(path=nb_path)
    assert len(nbs) == 1


def test_get_notebook_md(crate, nb_path):
    nbs = crate.get_notebooks(path=nb_path)
    metadata = crate.get_nb_metadata(nbs[0])
    assert metadata["name"] == "My test notebook"


def test_get_page_title(crate, monkeypatch):
    def mock_get(*args, **kwargs):
        return PageResponse()

    monkeypatch.setattr(requests, "get", mock_get)

    title = crate.get_page_title("https://mycoolsite.com")
    assert title == "An interesting web page"


def test_add_python_version(monkeypatch, crate):

    monkeypatch.setattr(sys, "version_info", (3, 10, 12))
    entity = crate.add_python_version()
    assert entity.__class__.__name__ == "ContextEntity"
    assert entity.id == "https://www.python.org/downloads/release/python-31012/"
    assert entity.type == ["ComputerLanguage", "SoftwareApplication"]
    assert entity["version"] == "3.10.12"
    assert crate.crate.get(entity.id).id == entity.id


def test_get_gh_parts(crate):
    urls = [
        "https://github.com/GLAM-Workbench/recordsearch",
        "https://github.com/GLAM-Workbench/recordsearch/blob/master/series_totals_May_2021.csv",
        "https://github.com/GLAM-Workbench/recordsearch/raw/refs/heads/master/data/A6119-items.csv",
        "https://raw.githubusercontent.com/GLAM-Workbench/recordsearch/refs/heads/master/data/A6119-items.csv",
    ]
    for url in urls:
        owner, repo = crate.get_gh_parts(url)
        assert owner == "GLAM-Workbench"
        assert repo == "recordsearch"


def test_get_gh_repo(monkeypatch, crate):
    def mock_repo(*args, **kwargs):
        return GitHubRepo(*args, **kwargs)

    monkeypatch.setattr(Github, "get_repo", mock_repo)
    repo = crate.get_gh_repo("https://github.com/GLAM-Workbench/recordsearch")
    assert repo.name == "recordsearch"


def test_get_gh_path(monkeypatch, crate):
    def mock_repo(*args, **kwargs):
        return "master"

    monkeypatch.setattr(crate, "get_default_gh_branch", mock_repo)
    path = crate.get_gh_path(
        "https://github.com/GLAM-Workbench/recordsearch/raw/refs/heads/master/data/A6119-items.csv"
    )
    assert path == "data/A6119-items.csv"


def test_get_repo_info(monkeypatch, crate):
    def fake_repo(*args, **kwargs):
        return GitRepo()

    monkeypatch.setattr(git, "Repo", fake_repo)
    repo_name, repo_url = crate.get_repo_info()
    assert repo_name == "recordsearch"
    assert repo_url == "https://github.com/GLAM-Workbench/recordsearch/"


def test_get_repo_info_exception(monkeypatch, crate, tmp_path):
    def fake_repo(*args, **kwargs):
        return Repo(tmp_path)

    monkeypatch.setattr(git, "Repo", fake_repo)
    repo_name, repo_url = crate.get_repo_info()
    assert repo_name == "example-repo"
    assert repo_url == ""


def test_get_repo_link(crate):
    entry = {
        "url": "https://github.com/GLAM-Workbench/recordsearch/raw/refs/heads/master/data/A6119-items.csv"
    }
    repo_url = crate.get_repo_link(entry)
    assert repo_url == "https://github.com/GLAM-Workbench/recordsearch"


def test_get_repo_link_no_url(monkeypatch, crate):
    def fake_repo_info(*args, **kwargs):
        return "recordsearch", "https://github.com/GLAM-Workbench/recordsearch"

    monkeypatch.setattr(crate, "get_repo_info", fake_repo_info)
    repo_url = crate.get_repo_link({})
    assert repo_url == "https://github.com/GLAM-Workbench/recordsearch"


def test_add_repo_link(crate):
    entry = {
        "url": "https://github.com/GLAM-Workbench/recordsearch/raw/refs/heads/master/data/A6119-items.csv"
    }
    entry = crate.add_repo_link(entry)
    assert entry["isPartOf"] == "https://github.com/GLAM-Workbench/recordsearch"


def test_get_gh_branch(monkeypatch, crate):
    def fake_gh_repo(*args, **kwargs):
        return GitHubRepo(full_name_or_id="GLAM-Workbench/recordsearch")

    monkeypatch.setattr(crate, "get_gh_repo", fake_gh_repo)
    branch = crate.get_default_gh_branch(
        "https://github.com/GLAM-Workbench/recordsearch"
    )
    assert branch == "master"


def test_get_gh_file_url(monkeypatch, crate):
    def fake_repo_info(*args, **kwargs):
        return "recordsearch", "https://github.com/GLAM-Workbench/recordsearch"

    def fake_gh_branch(*args, **kwargs):
        return "master"

    monkeypatch.setattr(crate, "get_repo_info", fake_repo_info)
    monkeypatch.setattr(crate, "get_default_gh_branch", fake_gh_branch)
    url = crate.get_gh_file_url("data/A6119-items.csv")
    assert (
        url
        == "https://github.com/GLAM-Workbench/recordsearch/blob/master/data/A6119-items.csv"
    )


def test_file_in_repo(crate):
    crate.data_repo = "https://github.com/GLAM-Workbench/trove-newspapers-non-english"
    assert crate.file_in_repo(
        {
            "url": "https://github.com/GLAM-Workbench/trove-newspapers-non-english/blob/main/newspapers_non_english.csv"
        }
    )


def test_add_files_web(monkeypatch, crate):
    def fake_web_stats(*args, **kwargs):
        return {"contentSize": 2456, "dateModified": "2025-05-21T06:24:13+00:00"}

    files = [
        {
            "url": "https://github.com/GLAM-Workbench/trove-newspapers-non-english/blob/main/newspapers_non_english.csv"
        }
    ]
    monkeypatch.setattr(crate, "get_web_file_stats", fake_web_stats)
    added = crate.add_files(files)
    assert added[0]["@id"] == files[0]["url"]
    assert added[0]["url"] == files[0]["url"]
    assert added[0]["contentSize"] == 2456


def test_add_files_web_local(crate, data_file):
    file_path = Path("test.csv")
    data_file.to_csv(file_path)
    files = [
        {
            "url": "https://github.com/GLAM-Workbench/trove-newspapers-non-english/blob/main/newspapers_non_english.csv",
            "localPath": str(file_path),
        }
    ]
    added = crate.add_files(files)
    assert added[0]["@id"] == files[0]["url"]
    assert added[0]["url"] == files[0]["url"]
    assert added[0]["size"] == data_file.shape[0] + 1
    assert isinstance(added[0]["contentSize"], int)
    file_path.unlink()


def test_add_files_local(crate, data_file):
    test_dir = Path("test-data")
    test_dir.mkdir()
    file_path = Path(test_dir, "test.csv")
    data_file.to_csv(file_path)
    files = [{"localPath": str(file_path)}]
    added = crate.add_files(files)
    assert added[0]["@id"] == str(file_path)
    assert added[0]["size"] == data_file.shape[0] + 1
    assert isinstance(added[0]["contentSize"], int)
    shutil.rmtree("test-data")


def test_get_gh_stats(monkeypatch, crate):
    def fake_gh_repo(*args, **kwargs):
        return GitHubRepo(full_name_or_id="GLAM-Workbench/recordsearch")

    monkeypatch.setattr(crate, "get_gh_repo", fake_gh_repo)
    stats = crate.get_web_file_stats(
        "https://github.com/GLAM-Workbench/trove-newspapers-non-english/blob/main/newspapers_non_english.csv"
    )
    assert list(stats.keys()) == ["sdDatePublished", "contentSize", "dateModified"]
    assert stats["dateModified"] == "2024-11-02T00:00:00"


def test_get_web_stats(monkeypatch, crate):
    def fake_headers(*args, **kwargs):
        return PageHead

    monkeypatch.setattr(requests, "head", fake_headers)
    stats = crate.get_web_file_stats("https://fake.url")
    assert list(stats.keys()) == ["sdDatePublished", "contentSize", "dateModified"]
    assert stats["dateModified"] == "2024-09-13T07:01:28+00:00"


def test_get_local_file_stats(crate, data_file):
    file_path = Path("test.csv")
    data_file.to_csv(file_path)
    stats = crate.get_local_file_stats(file_path)
    assert list(stats.keys()) == [
        "sdDatePublished",
        "contentSize",
        "dateModified",
        "size",
    ]
    assert stats["size"] == data_file.shape[0] + 1
    assert isinstance(stats["contentSize"], int)
    file_path.unlink()


def test_get_local_dir_stats(crate, data_file):
    test_dir = Path("test-data")
    test_dir.mkdir()
    file_path = Path(test_dir, "test.csv")
    data_file.to_csv(file_path)
    stats = crate.get_local_file_stats(test_dir)
    assert stats["size"] == 1
    shutil.rmtree("test-data")


def test_update_properties(monkeypatch, crate):
    def fake_add_entities(entry, key, value):
        entry[key] = delistify(value)
        return entry

    entry = {"@type": "Person"}
    updates = {
        "mainEntityOfPage": "https://glam-workbench.net",
        "extra": "Another value",
        "@type": "Crocodile",
    }
    monkeypatch.setattr(crate, "add_entities", fake_add_entities)
    entry = crate.update_properties(entry, updates, exclude=["extra"])
    assert entry["mainEntityOfPage"] == "https://glam-workbench.net"
    assert "extra" not in entry
    assert entry.get("@type") == "Person"


def test_add_people_orcid(crate):
    people = [
        {"name": "Sherratt, Tim", "orcid": "https://orcid.org/0000-0001-7956-4498"}
    ]
    added = crate.add_people(people)
    assert added[0].id == people[0]["orcid"]
    assert added[0].type == "Person"
    assert crate.crate.get(added[0].id) != None


def test_add_people_no_orcid(crate):
    people = [
        {
            "name": "Sherratt, Tim",
        }
    ]
    added = crate.add_people(people)
    assert added[0].id == "#Sherratt_Tim"
    assert added[0].type == "Person"
    assert crate.crate.get(added[0].id) != None


def test_add_people_orcid_str(crate):
    people = [{"name": "Sherratt, Tim", "orcid": "0000-0001-7956-4498"}]
    added = crate.add_people(people)
    assert added[0].id == f"https://orcid.org/0000-0001-7956-4498"
    assert added[0].type == "Person"
    assert crate.crate.get(added[0].id) != None


def test_add_update_action(crate):
    crate.add_update_action("v1.0")
    version = crate.crate.get("create_version_v1_0")
    assert version is not None
    assert version["name"] == "Create version v1.0"


def test_add_context_entity(crate):
    data = {
        "@id": "https://glam-workbench.net/",
        "@type": "CreativeWork",
        "name": "GLAM Workbench",
        "url": "https://glam-workbench.net/",
    }
    entity = crate.add_context_entity(data)
    assert crate.crate.get(data["@id"]) != None
    assert entity.id == data["@id"]


def test_add_page_str(monkeypatch, crate):
    def fake_page_title(*args, **kwargs):
        return "GLAM Workbench"

    monkeypatch.setattr(crate, "get_page_title", fake_page_title)
    page_data = "https://glam-workbench.net/"
    page = crate.add_page(page_data)
    assert crate.crate.get(page_data) != None
    assert page.id == page_data
    assert page["name"] == "GLAM Workbench"


def test_add_page(crate):
    page_data = {"url": "https://glam-workbench.net/", "name": "GLAM Workbench is cool"}
    page = crate.add_page(page_data)
    assert crate.crate.get(page_data["url"]) != None
    assert page.id == page_data["url"]
    assert page["name"] == "GLAM Workbench is cool"


def test_update_page(crate):
    page_data1 = {"url": "https://glam-workbench.net/", "name": "GLAM Workbench"}
    page_data2 = {
        "url": "https://glam-workbench.net/",
        "name": "GLAM Workbench is cool",
    }
    crate.add_page(page_data1)
    page2 = crate.add_page(page_data2)
    assert page2["name"] == "GLAM Workbench is cool"


def test_add_pages(crate):
    page_data = [
        {"url": "https://glam-workbench.net/", "name": "GLAM Workbench"},
        {"url": "https://timsherratt.au", "name": "Tim Sherratt's home page"},
    ]
    pages = crate.add_pages(page_data)
    assert len(pages) == 2
    assert crate.crate.get(page_data[0]["url"]) != None


def test_add_licence(crate):
    licences = ["mit"]
    added = crate.add_licence(licences)
    assert crate.crate.get(LICENCES[licences[0]]["@id"]) != None
    assert added[0].id == LICENCES[licences[0]]["@id"]


def test_add_download(crate):
    downloads = [
        "https://github.com/GLAM-Workbench/trove-newspapers-non-english/archive/refs/heads/main.zip"
    ]
    added = crate.add_download(downloads)
    assert added[0].id == downloads[0]


def test_filter_files(crate, action_data):
    assert len(crate.filter_files(action_data, "result")) == 1
    assert len(crate.filter_files(action_data, "object")) == 0


def test_filter_files_data_repo(crate, action_data):
    crate.data_repo = "https://github.com/GLAM-Workbench/trove-newspapers-non-english/"
    assert len(crate.filter_files(action_data, "result")) == 1
    assert len(crate.filter_files(action_data, "object")) == 0


def test_add_actions(monkeypatch, crate, action_data, notebook):
    def fake_files(*args, **kwargs):
        files = [
            {
                "@id": "https://github.com/GLAM-Workbench/trove-newspapers-non-english/blob/main/newspapers_non_english.csv",
                "url": "https://github.com/GLAM-Workbench/trove-newspapers-non-english/blob/main/newspapers_non_english.csv",
                "dateModified": "2025-05-05",
            }
        ]
        return files

    monkeypatch.setattr(crate, "add_files", fake_files)
    actions = crate.add_actions(notebook, [action_data])
    assert actions[0]["@type"] == "CreateAction"
    assert crate.crate.get("#test_notebook_run_0") is not None


def test_add_notebook(monkeypatch, crate, nb_path):
    def fake_get_gh_file_url(*args, **kwargs):
        return "https://github.com/GLAM-Workbench/trove-newspapers/blob/master/test_nb.ipynb"

    def fake_add_repo_link(nb_metadata):
        nb_metadata["isPartOf"] = "https://github.com/GLAM-Workbench/trove-newspapers/"
        return nb_metadata

    monkeypatch.setattr(crate, "add_repo_link", fake_add_repo_link)
    monkeypatch.setattr(crate, "get_gh_file_url", fake_get_gh_file_url)

    for nb_file in crate.get_notebooks(nb_path):
        nb = crate.add_notebook(nb_file)
        assert nb.id == "test_nb.ipynb"
        assert nb.get("name") == "My test notebook"
        assert (
            nb["isPartOf"]["@id"]
            == "https://github.com/GLAM-Workbench/trove-newspapers/"
        )
        assert crate.crate.get("test_nb.ipynb") is not None


def test_get_old_crate_data(crate, crate_path):
    root_props, entities, versions = crate.get_old_crate_data(crate_path)
    assert root_props["name"] == "My ROCrate"
    assert "mainEntityOfPage" in entities
    assert entities.get("mainEntityOfPage").id == "https://glam-workbench.net/trove-newspapers/"
    assert versions[0].id == "create_version_v_1_0"


@pytest.fixture
def fake_repo_info(*args, **kwargs):
    return "trove-newspapers", "https://github.com/GLAM-Workbench/trove-newspapers/"

def test_prepare_code_crate(monkeypatch, crate, fake_repo_info):
    def fake_get_old_crate_data(*args, **kwargs):
        return {}, {}, []
    def fake_get_repo_info(*args, **kwargs):
        return "trove-newspapers", "https://github.com/GLAM-Workbench/trove-newspapers/"
    crate.defaults = {}
    monkeypatch.setattr(crate, "get_old_crate_data", fake_get_old_crate_data)
    monkeypatch.setattr(crate, "get_repo_info", fake_get_repo_info)

    root_props, crate_source, entities, versions = crate.prepare_code_crate()
    assert root_props["name"] == "trove-newspapers"
    assert crate_source == "./"

def test_prepare_data_crate(monkeypatch, crate):
    def fake_get_old_crate_data(*args, **kwargs):
        return {}, {}, []
    def fake_get_gh_parts(*args, **kwargs):
        return "", "trove-newspapers-non-english"
    def fake_get_repo_info(*args, **kwargs):
        return "trove-newspapers", "https://github.com/GLAM-Workbench/trove-newspapers/"
    crate.defaults = {}
    crate.data_repo = "https://github.com/GLAM-Workbench/trove-newspapers-non-english/"
    monkeypatch.setattr(crate, "get_old_crate_data", fake_get_old_crate_data)
    monkeypatch.setattr(crate, "get_gh_parts", fake_get_gh_parts)
    monkeypatch.setattr(crate, "get_repo_info", fake_get_repo_info)
    root_props, crate_source, entities, versions = crate.prepare_data_crate()
    assert root_props["name"] == "trove-newspapers-non-english"
    assert crate_source == "./trove-newspapers-non-english-rocrate"
