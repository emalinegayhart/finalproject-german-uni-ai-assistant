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

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'default-secret-key')

def extract_costs(text):
    """extract cost information from text."""
    # look for numbers followed by € or eur
    costs = re.findall(r'(\d+(?:,\d+)?)\s*(?:€|EUR)', text)
    if costs:
        return int(costs[0].replace(',', ''))
    return 1000  # default cost if none found

def get_program_recommendations(interests, level, language_level, budget):
    """search for study programs using duckduckgo, focusing on daad database."""
    try:
        logger.info("="*50)
        logger.info("starting new search")
        logger.info(f"parameters: interests={interests}, level={level}, language={language_level}, budget={budget}")
        
        query = f"site:daad.de/en/study-and-research-in-germany/courses-of-study-in-germany {interests} {level} degree program"
        logger.info(f"search query: {query}")
        
        recommendations = []
        
        def search_with_timeout():
            max_retries = 3
            retry_delay = 5
            
            for attempt in range(max_retries):
                try:
                    with DDGS() as ddgs:
                        # add a small delay before the request
                        time.sleep(2)
                        return list(ddgs.text(
                            query,
                            safesearch='off',
                            max_results=10
                        ))
                except DuckDuckGoSearchException as e:
                    if "Ratelimit" in str(e):
                        if attempt < max_retries - 1:
                            logger.warning(f"rate limited, waiting {retry_delay} seconds before retry {attempt + 1}/{max_retries}")
                            time.sleep(retry_delay)
                            retry_delay *= 2
                            continue
                    raise
                except Exception as e:
                    logger.error(f"unexpected error during search: {str(e)}")
                    raise
            
            return []

        try:
            logger.info("initializing duckduckgo search with timeout...")
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(search_with_timeout)
                start_time = time.time()
                
                try:
                    search_results = future.result(timeout=90)  # increased timeout to 90 seconds to account for retries
                    end_time = time.time()
                    logger.info(f"search completed in {end_time - start_time:.2f} seconds")
                    logger.info(f"number of raw results: {len(search_results)}")
                    
                except TimeoutError:
                    logger.error("search timed out after 90 seconds")
                    return []
                
                if not search_results:
                    logger.warning("no search results found!")
                    return []
                
                for i, result in enumerate(search_results, 1):
                    try:
                        logger.info(f"\nprocessing result {i}:")
                        logger.info(f"title: {result.get('title', 'no title')}")
                        logger.info(f"link: {result.get('link', 'no link')}")
                        logger.info(f"snippet: {result.get('body', 'no body')[:100]}...")
                        
                        title = result['title']
                        link = result['link']
                        snippet = result['body']
                        
                        # extract university name
                        university = title.split(' - ')[0] if ' - ' in title else title
                        logger.info(f"extracted university: {university}")
                        
                        # extract city
                        city_match = re.search(r'\((.*?)\)', title)
                        city = city_match.group(1) if city_match else "various cities"
                        logger.info(f"extracted city: {city}")
                        
                        # extract program name
                        program_parts = title.split(' - ')
                        program_name = program_parts[1] if len(program_parts) > 1 else program_parts[0]
                        logger.info(f"extracted program name: {program_name}")
                        
                        # extract costs
                        monthly_costs = extract_costs(snippet)
                        logger.info(f"extracted monthly costs: {monthly_costs}€")
                        
                        # only add programs that fit within budget
                        if monthly_costs <= budget:
                            recommendation = {
                                "programName": program_name[:100],
                                "university": university[:100],
                                "city": city[:50],
                                "requirements": f"language level: {language_level}, details: {link}",
                                "monthlyCosts": monthly_costs,
                                "explanation": snippet[:200] + "..."
                            }
                            recommendations.append(recommendation)
                            logger.info("added recommendation to list")
                        else:
                            logger.info(f"skipped - cost {monthly_costs}€ exceeds budget {budget}€")
                            
                    except Exception as e:
                        logger.error(f"error processing result {i}: {str(e)}")
                        continue
                
                logger.info(f"\nfinal number of recommendations: {len(recommendations)}")
                return recommendations[:3]  # return top 3 results
                
        except Exception as e:
            logger.error(f"error during duckduckgo search: {str(e)}")
            raise
            
    except Exception as e:
        logger.error(f"error in get_program_recommendations: {str(e)}")
        logger.exception("full traceback:")
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
            logger.error("no data provided in request")
            return jsonify({"error": "no data provided"}), 400
            
        logger.info(f"received request data: {data}")
        
        required_fields = ['interests', 'level', 'language_level', 'budget']
        for field in required_fields:
            if field not in data:
                logger.error(f"missing required field: {field}")
                return jsonify({"error": f"missing required field: {field}"}), 400
        
        recommendations = get_program_recommendations(
            data.get('interests'),
            data.get('level'),
            data.get('language_level'),
            int(data.get('budget', 0))
        )
        
        logger.info(f"returning recommendations: {recommendations}")
        
        if not recommendations:
            return jsonify([])
            
        return jsonify(recommendations)
        
    except Exception as e:
        logger.error(f"error in recommend endpoint: {str(e)}")
        logger.exception("full traceback:")
        return jsonify({"error": "internal server error"}), 500

if __name__ == '__main__':
    app.run(debug=True)
