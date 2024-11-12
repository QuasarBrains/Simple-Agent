import os
from typing import List, Literal, cast
from memory.vector_store import VectorStore, Record
import requests
from rich.console import Console
import frontmatter

console = Console()

svs_url = ""
svs_directory = ""
svs_name = ""


def query_simple_vector_store(query: str) -> List[Record]:
    response = requests.post(
        f"{svs_url}/stores/{svs_name}/search",
        json={"query": query, "limit": 3, "threshold": 0.4},
    )
    if not response.ok:
        raise ValueError("Error querying store")

    records = []

    data = response.json()
    results = data["data"]
    for result in results:
        file_path = f"{svs_directory}/{result['title']}.md"
        with open(file_path, "r") as file:
            fm = frontmatter.load(file)
            importance_value = fm.get("importance", "low")
            importance: Literal["low", "medium", "high", "extreme"] = cast(
                Literal["low", "medium", "high", "extreme"], str(importance_value)
            )
            record_type = fm.get("type", "")
            print("record type: ", record_type)
            record = Record(
                id=result["id"],
                title=result["title"],
                content=result["content"],
                similarity=result["distance"],
                importance=importance,
                type=str(record_type),
            )
            records.append(record)

    return records


def add_simple_vector_store_record(record: Record) -> None:
    # create a new markdown file in the svs directory with importance and type as metadata
    try:
        with open(f"{svs_directory}/{record.title}.md", "w") as f:
            f.write(
                f"---\nimportance: {record.importance}\ntype: {record.type}\n---\n# {record.title}\n{record.content}"
            )
        sync_svs_store(svs_name)
    except Exception as e:
        raise ValueError("Error adding record", e)


def test_svs_store_exists(name: str):
    try:
        with console.status("[bold blue]Checking store...", spinner="dots12"):
            response = requests.get(f"{svs_url}/stores/{name}")
        if not response.ok:
            return False
        if (
            "path" in response.json()["data"]
            and response.json()["data"]["path"] == svs_directory
        ):
            return True
        return False
    except Exception as e:
        raise ValueError(f"Error checking store: {e}")
        return False


def create_svs_store(name: str):
    try:
        with console.status("[bold blue]Creating store...", spinner="dots12"):
            response = requests.post(
                f"{svs_url}/stores", json={"name": name, "path": svs_directory}
            )
        if not response.ok:
            raise ValueError("Error creating store")

    except Exception as e:
        raise ValueError("Error creating store", e)


def sync_svs_store(name: str):
    try:
        with console.status("[bold blue]Syncing store...", spinner="dots12"):
            response = requests.post(f"{svs_url}/stores/{name}/sync")
        if not response.ok:
            raise ValueError("Error syncing store")

    except Exception as e:
        raise ValueError("Error syncing store", e)


def build_svs_store(name: str):
    try:
        with console.status("[bold blue]Building store...", spinner="dots12"):
            response = requests.post(f"{svs_url}/stores/{name}/build")
        if not response.ok:
            raise ValueError("Error building store")

    except Exception as e:
        raise ValueError("Error building store", e)


def on_svs_init():
    try:
        global svs_url
        global svs_directory
        global svs_name

        svs_url = os.environ.get("SIMPLE_VECTOR_STORE_URL", "")
        if not svs_url:
            raise ValueError("SIMPLE_VECTOR_STORE_URL not set")

        svs_directory = os.environ.get("SIMPLE_VECTOR_STORE_DIRECTORY", "")
        if not svs_directory:
            raise ValueError("SIMPLE_VECTOR_STORE_DIRECTORY not set")

        svs_name = os.environ.get("SIMPLE_VECTOR_STORE_NAME", "")
        if not svs_name:
            raise ValueError("SIMPLE_VECTOR_STORE_NAME not set")

        if not test_svs_store_exists(svs_name):
            create_svs_store(svs_name)
            build_svs_store(svs_name)
        else:
            sync_svs_store(svs_name)
    except Exception as e:
        raise ValueError("Error initializing simple vector store", e)


SVSVectorStore = VectorStore(
    name="simple_vector_store",
    query_store=query_simple_vector_store,
    add_record=add_simple_vector_store_record,
    on_startup=on_svs_init,
)
