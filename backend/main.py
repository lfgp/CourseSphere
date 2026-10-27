from openai import OpenAI
import json
import secrets as st
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent

def hashFunction(data) -> str:
    """Generate an opaque message ID; this function is not a password hash."""
    return st.token_hex(32)


def make_prompt(query: str):
    with (BACKEND_DIR / "query_types.json").open(encoding="utf-8") as file:
        question_types = json.load(file)
    return ("""
    Respond to this prompt with a JSON object ONLY! No other output.
                    
    Consider the following query types with parameters:"""
    + str(question_types)
    + """
    The keys in the parameter list represent the paremeters, and the values of those keys
    represent the data types that those parameters are.
    
    Given the following query:"""
    +  query
    + """, identify which query type it is and what
        the relevant parameters are.

        Print the output as a JSON object of the following form:

        {
            "query_type": ....,
            "parameters": ....
        }

        If the query is empty or doesn't make sense, say that it is an unsupported query_type
    """)

def get_query_details(query: str) -> dict:
    with (BACKEND_DIR / "config.json").open(encoding="utf-8") as file:
        config = json.load(file)
    client = OpenAI(api_key=config['openai_api_key'])
    response = client.completions.create(
        model = "gpt-3.5-turbo-instruct",
        prompt = make_prompt(query),
        max_tokens=1000
    )
    return json.loads(response.to_dict()['choices'][0]['text'])
if __name__ == "__main__":
    response = get_query_details("")
    print(response)
