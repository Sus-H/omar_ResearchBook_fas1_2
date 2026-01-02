#!/usr/bin/env python3
"""
Test script to identify which database is which
"""

from neo4j import GraphDatabase

def test_database(uri, username, password, db_name):
    """Test a database and show what it contains"""
    print(f"\n{'='*60}")
    print(f"Testing: {uri}")
    print(f"{'='*60}")
    
    driver = GraphDatabase.driver(uri, auth=(username, password))
    
    try:
        with driver.session(database="neo4j") as session:
            # Test connection
            print("✅ Connection successful!")
            
            # Get node labels
            labels_query = "CALL db.labels()"
            labels_result = session.run(labels_query)
            labels = [record['label'] for record in labels_result]
            
            print(f"\n📊 Node types found: {labels}")
            
            # Count nodes by label
            print(f"\n📈 Node counts:")
            for label in labels:
                count_query = f"MATCH (n:{label}) RETURN count(n) as count"
                count_result = session.run(count_query)
                count = count_result.single()['count']
                print(f"   {label}: {count:,}")
            
            # Get relationship types
            rel_types_query = "CALL db.relationshipTypes()"
            rel_types_result = session.run(rel_types_query)
            rel_types = [record['relationshipType'] for record in rel_types_result]
            
            print(f"\n🔗 Relationship types: {rel_types}")
            
            # Show sample data
            print(f"\n🔍 Sample data:")
            for label in labels[:3]:  # First 3 labels
                sample_query = f"""
                MATCH (n:{label})
                RETURN n LIMIT 1
                """
                sample_result = session.run(sample_query)
                sample = sample_result.single()
                if sample:
                    node_data = dict(sample['n'])
                    # Show just the keys/properties
                    print(f"   {label} properties: {list(node_data.keys())}")
            
            # Determine database type based on content
            print(f"\n🎯 Database identification:")
            if 'Thesis' in labels:
                print("   ➡️  This appears to be the THESIS RELATIONSHIPS database (DB2)")
                print("      Contains thesis supervision and examination data")
            elif 'Publication' in labels or 'Organization' in labels:
                print("   ➡️  This appears to be the RESEARCH INTELLIGENCE database (DB1)")
                print("      Contains ORCID and Chalmers research data")
            else:
                print("   ❓ Unable to automatically identify database type")
                
    except Exception as e:
        print(f"❌ Connection failed: {e}")
    finally:
        driver.close()

if __name__ == "__main__":
    print("\n🔬 ResearchBook Database Identifier")
    print("="*60)
    
    # Credentials
    username = "neo4j"
    password = "password123"
    
    # Test both databases
    test_database(
        "bolt+s://graphdb.ita.chalmers.se:7689",
        username,
        password,
        "Database 1 (7689)"
    )
    
    test_database(
        "bolt+s://graphdb.ita.chalmers.se:7688",
        username,
        password,
        "Database 2 (7688)"
    )
    
    print("\n" + "="*60)
    print("Summary:")
    print("="*60)
    print("DB1 (Research Intelligence) should have: Person, Publication, Organization")
    print("DB2 (Thesis Relationships) should have: Person, Thesis")
    print("\nUpdate your .env file accordingly!")
