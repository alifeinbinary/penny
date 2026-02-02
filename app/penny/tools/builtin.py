"""Built-in tools."""

import time

from perplexity import Perplexity

from penny.tools.base import Tool


class PerplexitySearchTool(Tool):
    """Tool for searching the web using Perplexity AI."""

    name = "perplexity_search"
    description = (
        "Search the web for current information using Perplexity AI. "
        "Use this when you need up-to-date information, facts, news, or "
        "answers to questions that require real-time data or information "
        "beyond your training data."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query or question to ask Perplexity",
            }
        },
        "required": ["query"],
    }

    def __init__(self, api_key: str, db=None):
        """
        Initialize the tool with Perplexity API key.

        Args:
            api_key: Perplexity API key
            db: Optional Database instance for logging searches
        """
        self.client = Perplexity(api_key=api_key)
        self.db = db

    async def execute(self, query: str, **kwargs) -> str:
        """
        Execute a search using Perplexity.

        Args:
            query: The search query

        Returns:
            Search results as a string
        """
        try:
            start = time.time()

            response = self.client.responses.create(
                preset="pro-search",
                input=query,
            )

            duration_ms = int((time.time() - start) * 1000)
            result = response.output_text if response.output_text else "No results found"

            if self.db:
                self.db.log_search(
                    query=query,
                    response=result,
                    duration_ms=duration_ms,
                )

            return result
        except Exception as e:
            return f"Error performing search: {str(e)}"
