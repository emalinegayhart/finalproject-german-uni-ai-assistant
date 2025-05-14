from duckduckgo_search import DDGS
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def test_search():
    query = "Computer Science Master Germany"
    logger.info(f"Testing search with query: {query}")
    
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))
            logger.info(f"Number of results: {len(results)}")
            
            for i, result in enumerate(results, 1):
                logger.info(f"\nResult {i}:")
                logger.info(f"Title: {result.get('title', 'No title')}")
                logger.info(f"Link: {result.get('link', 'No link')}")
                logger.info(f"Snippet: {result.get('body', 'No body')[:100]}...")
                
    except Exception as e:
        logger.error(f"Error during search: {str(e)}")
        logger.exception("Full traceback:")

if __name__ == "__main__":
    test_search() 