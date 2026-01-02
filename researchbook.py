#!/usr/bin/env python3
"""
ResearchBook - Academic Intelligence Platform
Using 2 Neo4j databases + LightLLM for research intelligence
"""

from neo4j import GraphDatabase
import requests
import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Any
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class ResearchBook:
    def __init__(self):
        # Database 1 - Research Intelligence (Chalmers + ORCID)
        self.db1_driver = GraphDatabase.driver(
            os.getenv("NEO4J_DB1_URI"),
            auth=(os.getenv("NEO4J_DB1_USERNAME"), os.getenv("NEO4J_DB1_PASSWORD"))
        )
        
        # Database 2 - Thesis Relationships  
        self.db2_driver = GraphDatabase.driver(
            os.getenv("NEO4J_DB2_URI"),
            auth=(os.getenv("NEO4J_DB2_USERNAME"), os.getenv("NEO4J_DB2_PASSWORD"))
        )
        
        # LightLLM API
        self.llm_url = os.getenv("LIGHTLLM_URL")
        self.llm_key = os.getenv("LIGHTLLM_API_KEY")
        self.llm_model = os.getenv("LIGHTLLM_MODEL", "claude-sonnet-4")
        
    def ai_query(self, prompt: str, max_tokens: int = 1000) -> str:
        """Send query to LightLLM and get AI response"""
        headers = {
            "Authorization": f"Bearer {self.llm_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.llm_model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": 0.3
        }
        
        try:
            response = requests.post(self.llm_url, headers=headers, json=payload, 
                                   timeout=30, verify=False)
            if response.status_code == 200:
                result = response.json()
                return result['choices'][0]['message']['content']
            else:
                return f"AI Error: {response.status_code}"
        except Exception as e:
            return f"AI Error: {e}"
    
    def lookup_person(self, name: str) -> Dict[str, Any]:
        """
        RESEARCHBOOK CORE FEATURE 1: Person Lookup
        Search person across both databases and generate AI profile
        """
        print(f"🔍 Looking up: {name}")
        
        # Database 1: Get researcher profile
        db1_profile = self._get_researcher_profile_db1(name)
        
        # Database 2: Get thesis involvement
        db2_profile = self._get_thesis_activities_db2(name)
        
        # Combine data
        combined_data = {
            "name": name,
            "found_in_db1": len(db1_profile) > 0,
            "found_in_db2": len(db2_profile) > 0,
            "researcher_data": db1_profile,
            "thesis_data": db2_profile
        }
        
        # Generate AI summary if we found data
        if combined_data["found_in_db1"] or combined_data["found_in_db2"]:
            ai_prompt = self._create_person_analysis_prompt(combined_data)
            combined_data["ai_analysis"] = self.ai_query(ai_prompt)
        else:
            combined_data["ai_analysis"] = "Person not found in either database"
        
        return combined_data
    
    def _get_researcher_profile_db1(self, name: str) -> List[Dict]:
        """Get researcher data from Database 1"""
        with self.db1_driver.session(database="neo4j") as session:
            query = """
            MATCH (p:Person)
            WHERE toLower(p.name) CONTAINS toLower($name)
            OPTIONAL MATCH (p)-[w:WORKED_AT]->(org:Organization)
            OPTIONAL MATCH (p)-[auth:AUTHORED]->(pub:Publication)
            RETURN p.name as name,
                   p.orcid_id as orcid_id,
                   p.orcid_given_names as given_names,
                   p.orcid_family_name as family_name,
                   p.orcid_publication_count as pub_count,
                   collect(DISTINCT {
                       organization: org.name,
                       role: w.role,
                       department: w.department,
                       start_year: w.start_year,
                       end_year: w.end_year
                   }) as affiliations,
                   count(DISTINCT pub) as total_publications
            LIMIT 10
            """
            
            result = session.run(query, name=name)
            profiles = []
            
            for record in result:
                profile = {
                    "name": record["name"],
                    "orcid_id": record["orcid_id"],
                    "given_names": record["given_names"], 
                    "family_name": record["family_name"],
                    "orcid_publication_count": record["pub_count"],
                    "total_publications": record["total_publications"],
                    "affiliations": [aff for aff in record["affiliations"] if aff["organization"]]
                }
                profiles.append(profile)
            
            return profiles
    
    def _get_thesis_activities_db2(self, name: str) -> List[Dict]:
        """Get thesis involvement from Database 2"""
        with self.db2_driver.session(database="neo4j") as session:
            query = """
            MATCH (p:Person)-[r]->(t:Thesis)
            WHERE toLower(p.name) CONTAINS toLower($name)
            RETURN p.name as person_name,
                   type(r) as relationship_type,
                   t.title as thesis_title,
                   t.type as thesis_type,
                   t.keywords as keywords,
                   t.abstract as abstract
            LIMIT 20
            """
            
            result = session.run(query, name=name)
            activities = []
            
            for record in result:
                activity = {
                    "person_name": record["person_name"],
                    "role": record["relationship_type"],
                    "thesis_title": record["thesis_title"],
                    "thesis_type": record["thesis_type"],
                    "keywords": record["keywords"] or [],
                    "abstract": record["abstract"] or ""
                }
                activities.append(activity)
            
            return activities
    
    def _create_person_analysis_prompt(self, person_data: Dict) -> str:
        """Create AI prompt for person analysis"""
        prompt = f"""
        Analyze this researcher profile and provide a comprehensive summary:

        RESEARCHER: {person_data['name']}
        
        DATABASE 1 (Research Profile):
        {json.dumps(person_data['researcher_data'], indent=2)}
        
        DATABASE 2 (Thesis Activities):  
        {json.dumps(person_data['thesis_data'], indent=2)}
        
        Please provide:
        1. Research expertise areas (based on thesis topics, roles, publications)
        2. Career progression summary (positions, institutions, timeline)
        3. Academic involvement (supervision, examination, collaboration patterns)
        4. Key strengths and specializations
        5. Overall academic profile assessment
        
        Keep response concise but comprehensive (max 500 words).
        """
        
        return prompt
    
    def find_expert(self, topic: str, limit: int = 10) -> Dict[str, Any]:
        """
        RESEARCHBOOK CORE FEATURE 2: Expert Finder
        Find experts on a topic across both databases with AI ranking
        """
        print(f"🎯 Finding experts on: {topic}")
        
        # Search Database 1
        db1_experts = self._search_experts_db1(topic, limit)
        
        # Search Database 2  
        db2_experts = self._search_experts_db2(topic, limit)
        
        # Combine and deduplicate
        all_experts = self._merge_expert_results(db1_experts, db2_experts)
        
        # AI ranking and analysis
        if all_experts:
            ranking_prompt = self._create_expert_ranking_prompt(topic, all_experts)
            ai_ranking = self.ai_query(ranking_prompt, max_tokens=1500)
        else:
            ai_ranking = f"No experts found for topic: {topic}"
        
        return {
            "topic": topic,
            "experts_found": len(all_experts),
            "db1_matches": len(db1_experts),
            "db2_matches": len(db2_experts),
            "expert_list": all_experts,
            "ai_ranking": ai_ranking
        }
    
    def _search_experts_db1(self, topic: str, limit: int) -> List[Dict]:
        """Search for experts in Database 1"""
        with self.db1_driver.session(database="neo4j") as session:
            # Search in publication keywords and abstracts
            query = """
            MATCH (p:Person)-[auth:AUTHORED]->(pub:Publication)
            WHERE toLower(pub.keywords) CONTAINS toLower($topic) OR
                  toLower(pub.abstract) CONTAINS toLower($topic) OR
                  toLower(pub.title) CONTAINS toLower($topic)
            WITH p, count(pub) as relevant_pubs, collect(pub.title)[..3] as sample_pubs
            MATCH (p)-[w:WORKED_AT]->(org:Organization)
            RETURN p.name as name,
                   p.orcid_id as orcid_id,
                   relevant_pubs,
                   sample_pubs,
                   collect(DISTINCT org.name)[..2] as organizations,
                   collect(DISTINCT w.department)[..2] as departments
            ORDER BY relevant_pubs DESC
            LIMIT $limit
            """
            
            result = session.run(query, topic=topic, limit=limit)
            experts = []
            
            for record in result:
                expert = {
                    "name": record["name"],
                    "orcid_id": record["orcid_id"],
                    "relevant_publications": record["relevant_pubs"],
                    "sample_publications": record["sample_pubs"],
                    "organizations": record["organizations"],
                    "departments": record["departments"],
                    "source": "database_1"
                }
                experts.append(expert)
            
            return experts
    
    def _search_experts_db2(self, topic: str, limit: int) -> List[Dict]:
        """Search for experts in Database 2"""
        with self.db2_driver.session(database="neo4j") as session:
            # Search thesis titles, keywords, abstracts
            query = """
            MATCH (p:Person)-[r]->(t:Thesis)
            WHERE toLower(t.title) CONTAINS toLower($topic) OR
                  any(keyword IN t.keywords WHERE toLower(keyword) CONTAINS toLower($topic)) OR
                  toLower(t.abstract) CONTAINS toLower($topic)
            WITH p, type(r) as role_type, count(t) as relevant_theses, 
                 collect(t.title)[..3] as sample_theses
            RETURN p.name as name,
                   collect(DISTINCT role_type) as roles,
                   relevant_theses,
                   sample_theses
            ORDER BY relevant_theses DESC
            LIMIT $limit
            """
            
            result = session.run(query, topic=topic, limit=limit)
            experts = []
            
            for record in result:
                expert = {
                    "name": record["name"],
                    "roles": record["roles"],
                    "relevant_theses": record["relevant_theses"],
                    "sample_theses": record["sample_theses"],
                    "source": "database_2"
                }
                experts.append(expert)
            
            return experts
    
    def _merge_expert_results(self, db1_experts: List[Dict], db2_experts: List[Dict]) -> List[Dict]:
        """Merge and deduplicate expert results from both databases"""
        merged = {}
        
        # Add DB1 experts
        for expert in db1_experts:
            name = expert["name"]
            merged[name] = expert
            merged[name]["combined_score"] = expert["relevant_publications"]
        
        # Add/merge DB2 experts
        for expert in db2_experts:
            name = expert["name"]
            if name in merged:
                # Merge data
                merged[name]["thesis_roles"] = expert["roles"]
                merged[name]["relevant_theses"] = expert["relevant_theses"]
                merged[name]["sample_theses"] = expert["sample_theses"]
                merged[name]["combined_score"] += expert["relevant_theses"] * 0.5  # Weight theses lower
                merged[name]["source"] = "both_databases"
            else:
                expert["combined_score"] = expert["relevant_theses"] * 0.5
                merged[name] = expert
        
        # Sort by combined score
        return sorted(merged.values(), key=lambda x: x["combined_score"], reverse=True)
    
    def _create_expert_ranking_prompt(self, topic: str, experts: List[Dict]) -> str:
        """Create AI prompt for expert ranking"""
        prompt = f"""
        Rank and analyze these experts for the topic: "{topic}"
        
        EXPERTS FOUND:
        {json.dumps(experts, indent=2)}
        
        Please provide:
        1. Top 5 experts ranked by relevance to "{topic}"
        2. For each expert, explain why they're qualified (publications, thesis work, roles)
        3. Identify any collaboration patterns or research networks
        4. Suggest which expert would be best for: media interviews, research collaboration, student supervision
        
        Format as a clear ranking with explanations.
        """
        
        return prompt
    
    def close_connections(self):
        """Close database connections"""
        self.db1_driver.close()
        self.db2_driver.close()

# Example usage
if __name__ == "__main__":
    rb = ResearchBook()
    
    # Test person lookup
    print("=== TESTING PERSON LOOKUP ===")
    person_result = rb.lookup_person("Anders")
    print(f"Found person: {person_result['name']}")
    print(f"In DB1: {person_result['found_in_db1']}, In DB2: {person_result['found_in_db2']}")
    if person_result['found_in_db1']:
        print(f"DB1 matches: {len(person_result['researcher_data'])}")
    if person_result['found_in_db2']:
        print(f"DB2 matches: {len(person_result['thesis_data'])}")
    print("AI Analysis:")
    print(person_result['ai_analysis'])
    
    print("\n" + "="*50 + "\n")
    
    # Test expert finder
    print("=== TESTING EXPERT FINDER ===")
    expert_result = rb.find_expert("machine learning")
    print(f"Topic: {expert_result['topic']}")
    print(f"Total experts found: {expert_result['experts_found']}")
    print(f"DB1 matches: {expert_result['db1_matches']}, DB2 matches: {expert_result['db2_matches']}")
    print("AI Ranking:")
    print(expert_result['ai_ranking'])
    
    rb.close_connections()