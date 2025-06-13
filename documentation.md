# Documentation



- author:
    - name (required)
    - orcid
    - mainEntityOfPage


Values in these fields can either be a url string or an object. If it's a url string it's converted to an object and a name is added from the page title. The objects are added as Context Entities.

- workExample:
    - url (required)
    - name: default = title of web page
    - description
- mainEntityOfPage:
    - url (required)
    - name: default = title of web page
- subjectOf
    - url (required)
    - name: default = title of web page


- license

rocrate root:

- name: default = name of GitHub repo
- description
- mainEntityOfPage: link to documentation
- author: default = authors from notebooks
- license
- codeRepository: (code repo) default = url of GitHub repo
- isBasedOn: (data repo) default = url of code GitHub repo
- action
- workExample?


CreateAction:

- 