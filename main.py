import os
from flask import Flask, render_template, request, jsonify
from duckduckgo_search import DDGS
from dotenv import load_dotenv
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import threading
from duckduckgo_search.exceptions import DuckDuckGoSearchException

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'default-secret-key')

def extract_costs(text):
    """Extract cost information from text."""
    # Look for numbers followed by € or EUR
    costs = re.findall(r'(\d+(?:,\d+)?)\s*(?:€|EUR)', text)
    if costs:
        # Convert first found cost to integer, removing commas
        return int(costs[0].replace(',', ''))
    return 1000  # Default cost if none found

def get_program_recommendations(interests, level, language_level, budget):
    """Search for study programs using DuckDuckGo."""
    try:
        logger.info("="*50)
        logger.info("Starting new search")
        logger.info(f"Parameters: interests={interests}, level={level}, language={language_level}, budget={budget}")
        
        # Construct search query - removed site:.de restriction and added more relevant terms
        query = f"{interests} {level} degree program university Germany studium"
        logger.info(f"Search query: {query}")
        
        recommendations = []
        
        def search_with_timeout():
            max_retries = 3
            retry_delay = 5  # Start with 5 seconds delay
            
            for attempt in range(max_retries):
                try:
                    with DDGS() as ddgs:
                        # Add a small delay before the request
                        time.sleep(2)
                        return list(ddgs.text(
                            query,
                            safesearch='off',
                            max_results=15
                        ))
                except DuckDuckGoSearchException as e:
                    if "Ratelimit" in str(e):
                        if attempt < max_retries - 1:  # Don't sleep on last attempt
                            logger.warning(f"Rate limited, waiting {retry_delay} seconds before retry {attempt + 1}/{max_retries}")
                            time.sleep(retry_delay)
                            retry_delay *= 2  # Double the delay for next attempt
                            continue
                    raise  # Re-raise if it's not a rate limit or we're out of retries
                except Exception as e:
                    logger.error(f"Unexpected error during search: {str(e)}")
                    raise
            
            return []  # Return empty list if all retries failed

        try:
            logger.info("Initializing DuckDuckGo search with timeout...")
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(search_with_timeout)
                start_time = time.time()
                
                try:
                    search_results = future.result(timeout=90)  # Increased timeout to 90 seconds to account for retries
                    end_time = time.time()
                    logger.info(f"Search completed in {end_time - start_time:.2f} seconds")
                    logger.info(f"Number of raw results: {len(search_results)}")
                    
                except TimeoutError:
                    logger.error("Search timed out after 90 seconds")
                    return []
                
                if not search_results:
                    logger.warning("No search results found!")
                    return []
                
                for i, result in enumerate(search_results, 1):
                    try:
                        logger.info(f"\nProcessing result {i}:")
                        logger.info(f"Title: {result.get('title', 'No title')}")
                        logger.info(f"Link: {result.get('link', 'No link')}")
                        logger.info(f"Snippet: {result.get('body', 'No body')[:100]}...")
                        
                        title = result['title']
                        link = result['link']
                        snippet = result['body']
                        
                        # Extract university name
                        university = title.split(' - ')[0] if ' - ' in title else title
                        logger.info(f"Extracted university: {university}")
                        
                        # Extract city
                        city_match = re.search(r'\((.*?)\)', title)
                        city = city_match.group(1) if city_match else "Various Cities"
                        logger.info(f"Extracted city: {city}")
                        
                        # Extract program name
                        program_parts = title.split(' - ')
                        program_name = program_parts[1] if len(program_parts) > 1 else program_parts[0]
                        logger.info(f"Extracted program name: {program_name}")
                        
                        # Extract costs
                        monthly_costs = extract_costs(snippet)
                        logger.info(f"Extracted monthly costs: {monthly_costs}€")
                        
                        # Only add programs that fit within budget
                        if monthly_costs <= budget:
                            recommendation = {
                                "programName": program_name[:100],
                                "university": university[:100],
                                "city": city[:50],
                                "requirements": f"Language level: {language_level}, Details: {link}",
                                "monthlyCosts": monthly_costs,
                                "explanation": snippet[:200] + "..."
                            }
                            recommendations.append(recommendation)
                            logger.info("Added recommendation to list")
                        else:
                            logger.info(f"Skipped - cost {monthly_costs}€ exceeds budget {budget}€")
                            
                    except Exception as e:
                        logger.error(f"Error processing result {i}: {str(e)}")
                        continue
                
                logger.info(f"\nFinal number of recommendations: {len(recommendations)}")
                return recommendations[:3]  # Return top 3 results
                
        except Exception as e:
            logger.error(f"Error during DuckDuckGo search: {str(e)}")
            raise
            
    except Exception as e:
        logger.error(f"Error in get_program_recommendations: {str(e)}")
        logger.exception("Full traceback:")
        return []

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/recommend', methods=['POST'])
def recommend():
    try:
        data = request.json
        if not data:
            logger.error("No data provided in request")
            return jsonify({"error": "No data provided"}), 400
            
        logger.info(f"Received request data: {data}")
        
        required_fields = ['interests', 'level', 'language_level', 'budget']
        for field in required_fields:
            if field not in data:
                logger.error(f"Missing required field: {field}")
                return jsonify({"error": f"Missing required field: {field}"}), 400
        
        recommendations = get_program_recommendations(
            data.get('interests'),
            data.get('level'),
            data.get('language_level'),
            int(data.get('budget', 0))
        )
        
        logger.info(f"Returning recommendations: {recommendations}")
        
        if not recommendations:
            return jsonify([])  # Return empty array instead of null
            
        return jsonify(recommendations)
        
    except Exception as e:
        logger.error(f"Error in recommend endpoint: {str(e)}")
        logger.exception("Full traceback:")
        return jsonify({"error": "Internal server error"}), 500

if __name__ == '__main__':
    app.run(debug=True)
