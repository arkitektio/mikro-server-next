import requests
import bs4
import json
from typing import Any
import re




def clean_extension(extension: str) -> str:
    lower_stripped = extension.strip().lower()
    if lower_stripped.startswith("."):
        return lower_stripped[1:]
    return lower_stripped

def description_to_clear(description: str) -> str:

    description = re.sub(r'\(.*\)', '', description)
    description = re.sub(r'\d+', '', description)
    description = description.strip()
    description = re.sub(r'\s+', '_', description)
    description = re.sub(r'[^a-zA-Z0-9_]', '', description)

    # delete all trailing underscores
    while description.endswith("_"):
        description = description[:-1]

    # delete all leading underscores
    while description.startswith("_"):
        description = description[1:]



    return description.strip().lower()




def load_bioimage_data() -> None:


    data = requests.get("https://bio-formats.readthedocs.io/en/v7.2.0/supported-formats.html").text
    # find the table 

    soup = bs4.BeautifulSoup(data, "html.parser")
    table = soup.find("table")

    # find the rows
    rows = table.find_all("tr")


    values: dict[str, dict[str, Any]] = {}



    for row in rows:
        cols = row.find_all("td")
        if len(cols) < 2:
            continue
        description = cols[0].text
        extensions = [clean_extension(e) for e in cols[1].text.split(",")]
        clear_description = description_to_clear(description)

        values[clear_description] = {
            "description": description,
            "extensions": extensions
        }

    print(values)

    json.dump(values, open("bioimage_data.json", "w"))



load_bioimage_data()