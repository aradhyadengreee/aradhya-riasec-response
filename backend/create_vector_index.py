# backend/create_vector_index.py
import os
import sys
from pymongo import MongoClient
from dotenv import load_dotenv

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

def create_vector_index():
    """
    Create vector search index in MongoDB Atlas for semantic search
    """
    MONGO_URI = os.getenv('MONGO_URI')
    
    if not MONGO_URI:
        print("❌ MONGO_URI not found in environment variables")
        print("Please create a .env file with MONGO_URI=your_connection_string")
        exit(1)
    
    try:
        # Connect to MongoDB Atlas
        print("🔗 Connecting to MongoDB Atlas...")
        client = MongoClient(MONGO_URI)
        db = client.career_counseling
        jobs_collection = db['jobs']
        
        # First check if collection exists and has data
        count = jobs_collection.count_documents({})
        print(f"📊 Total documents in 'jobs' collection: {count}")
        
        if count == 0:
            print("❌ No documents found in 'jobs' collection.")
            print("Please run import_script.py first to import data.")
            client.close()
            return
        
        # Check if embedding field exists
        sample_doc = jobs_collection.find_one({"embedding": {"$exists": True}})
        if not sample_doc:
            print("❌ No 'embedding' field found in documents.")
            print("Please run import_script.py with the updated version that creates embeddings.")
            client.close()
            return
        
        embedding_length = len(sample_doc.get('embedding', []))
        print(f"📏 Embedding dimension found: {embedding_length}")
        
        # Drop existing vector index if it exists
        print("🗑️  Checking for existing vector index...")
        existing_indexes = jobs_collection.index_information()
        vector_index_name = 'career_vectors'
        
        if vector_index_name in existing_indexes:
            print(f"⚠️  Existing vector index '{vector_index_name}' found. Dropping...")
            jobs_collection.drop_index(vector_index_name)
            print(f"✅ Dropped existing index '{vector_index_name}'")
        
        # Create vector search index
        print("\n🔨 Creating vector search index...")
        
        # For MongoDB Atlas 7.0+ with vector search
        create_index_command = {
            "createIndexes": "jobs",
            "indexes": [
                {
                    "name": vector_index_name,
                    "key": {
                        "embedding": "vector"
                    },
                    "vectorOptions": {
                        "type": "vector",
                        "dimensions": embedding_length,
                        "similarity": "cosine"
                    }
                }
            ]
        }
        
        try:
            result = db.command(create_index_command)
            print(f"✅ Vector search index '{vector_index_name}' created successfully!")
            print(f"   Dimensions: {embedding_length}")
            print(f"   Similarity: cosine")
        except Exception as e:
            print(f"⚠️  Could not create vector index with new method: {e}")
            print("\n📋 Trying alternative method for older MongoDB versions...")
            
            # Alternative method for older MongoDB versions
            try:
                jobs_collection.create_index(
                    [("embedding", "vector")],
                    name=vector_index_name,
                    vectorOptions={
                        "type": "vector",
                        "dimensions": embedding_length,
                        "similarity": "cosine"
                    }
                )
                print(f"✅ Vector search index '{vector_index_name}' created (alternative method)!")
            except Exception as alt_e:
                print(f"❌ Could not create vector index: {alt_e}")
                print("\n💡 You might need to create the index manually in MongoDB Atlas:")
                print("1. Go to MongoDB Atlas -> Search -> Create Search Index")
                print("2. Use JSON Editor and paste:")
                print("""
{
  "fields": [
    {
      "type": "vector",
      "path": "embedding",
      "numDimensions": %d,
      "similarity": "cosine"
    }
  ]
}
                """ % embedding_length)
                client.close()
                return
        
        # Verify the index was created
        print("\n🔍 Verifying index creation...")
        updated_indexes = jobs_collection.index_information()
        
        if vector_index_name in updated_indexes:
            print(f"✅ Index verification: '{vector_index_name}' is present in collection indexes")
            print(f"📋 All indexes in 'jobs' collection:")
            for idx_name in updated_indexes:
                print(f"   - {idx_name}")
        else:
            print(f"⚠️  Warning: '{vector_index_name}' not found in indexes after creation")
            print("   The index might be created asynchronously. Check MongoDB Atlas UI.")
        
        # Test vector search
        print("\n🧪 Testing vector search...")
        test_pipeline = [
            {
                "$vectorSearch": {
                    "index": vector_index_name,
                    "path": "embedding",
                    "queryVector": [0.1] * embedding_length,  # Dummy vector
                    "numCandidates": 10,
                    "limit": 3
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "job_id": 1,
                    "nco_title": 1,
                    "score": {"$meta": "vectorSearchScore"}
                }
            }
        ]
        
        try:
            test_results = list(jobs_collection.aggregate(test_pipeline, maxTimeMS=10000))
            if test_results:
                print(f"✅ Vector search test successful! Found {len(test_results)} results")
                for result in test_results[:2]:
                    print(f"   - {result.get('job_id')}: {result.get('nco_title')} (score: {result.get('score', 0):.3f})")
            else:
                print("⚠️  Vector search test returned no results")
        except Exception as test_e:
            print(f"⚠️  Vector search test failed: {test_e}")
            print("   This might be normal if the index is still building.")
        
        client.close()
        print("\n🎉 Vector index setup completed!")
        print("\n📝 Next steps:")
        print("1. Run your Flask application")
        print("2. Test the recommendations endpoint")
        print("3. Check if match percentages have improved")
        
    except Exception as e:
        print(f"\n❌ Error creating vector index: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("="*60)
    print("🔧 MongoDB Vector Search Index Creator")
    print("="*60)
    
    create_vector_index()