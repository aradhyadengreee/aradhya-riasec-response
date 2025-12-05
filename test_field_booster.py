#!/usr/bin/env python3
"""
Test script to verify the field booster functionality in the recommendation service.
This script tests various scenarios to ensure field matching works correctly.
"""

import sys
import os
import logging

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set up logging to see debug messages
logging.basicConfig(
    level=logging.DEBUG,
    format='%(levelname)s - %(name)s - %(message)s'
)

print("=" * 80)
print("🧪 FIELD BOOSTER TEST SUITE")
print("=" * 80)

# Test cases
test_cases = [
    {
        "name": "Test 1: Exact Field Match in Title",
        "user_profile": {
            "current_field": "Healthcare",
            "riasec_code": "SAI",
            "interests": ["Healthcare and Wellness"],
            "aptitude_percentiles": {"Social/Helping": 85, "Scientific": 80}
        },
        "job": {
            "job_id": "test_001",
            "nco_title": "Healthcare Administrator",
            "family_title": "Healthcare Management",
            "job_description": "Manage healthcare facilities and staff",
            "riasec_code": "SAI",
            "primary_interest_cluster": "Healthcare and Wellness",
            "aptitude_scores": {"Social/Helping": 80, "Scientific": 75},
            "primary_skills": ["Management", "Healthcare Administration"]
        },
        "expected_field_boost": 0.15,
        "should_match": True
    },
    {
        "name": "Test 2: Keyword Match (Computer Science -> Technology)",
        "user_profile": {
            "current_field": "Computer Science",
            "riasec_code": "IRC",
            "interests": ["Technology and Innovation"],
            "aptitude_percentiles": {"Digital/Computer": 90}
        },
        "job": {
            "job_id": "test_002",
            "nco_title": "Software Developer",
            "family_title": "Technology Professionals",
            "job_description": "Develop software applications and systems using computer programming",
            "riasec_code": "IRC",
            "primary_interest_cluster": "Technology and Innovation",
            "aptitude_scores": {"Digital/Computer": 85},
            "primary_skills": ["Programming", "Software Development"]
        },
        "expected_field_boost": 0.15,
        "should_match": True
    },
    {
        "name": "Test 3: No Match - Different Fields",
        "user_profile": {
            "current_field": "Marketing",
            "riasec_code": "EAS",
            "interests": ["Business and Entrepreneurship"],
            "aptitude_percentiles": {"Leadership/Persuasion": 88}
        },
        "job": {
            "job_id": "test_003",
            "nco_title": "Civil Engineer",
            "family_title": "Engineering Professionals",
            "job_description": "Design and oversee construction projects",
            "riasec_code": "RIC",
            "primary_interest_cluster": "Engineering and Technical Skills",
            "aptitude_scores": {"Mechanical": 85, "Spatial/Design": 80},
            "primary_skills": ["CAD", "Structural Analysis"]
        },
        "expected_field_boost": 0.0,
        "should_match": False
    },
    {
        "name": "Test 4: Partial Match in Description",
        "user_profile": {
            "current_field": "Finance",
            "riasec_code": "CEI",
            "interests": ["Finance and Economics"],
            "aptitude_percentiles": {"Numerical": 92}
        },
        "job": {
            "job_id": "test_004",
            "nco_title": "Investment Analyst",
            "family_title": "Financial Professionals",
            "job_description": "Analyze financial data and investment opportunities for clients",
            "riasec_code": "CEI",
            "primary_interest_cluster": "Finance and Economics",
            "aptitude_scores": {"Numerical": 90},
            "primary_skills": ["Financial Analysis", "Data Analysis"]
        },
        "expected_field_boost": 0.15,
        "should_match": True
    },
    {
        "name": "Test 5: Multi-word Field Match (Data Science)",
        "user_profile": {
            "current_field": "Data Science",
            "riasec_code": "ICA",
            "interests": ["Technology and Innovation", "Science and Research"],
            "aptitude_percentiles": {"Numerical": 95, "Digital/Computer": 92}
        },
        "job": {
            "job_id": "test_005",
            "nco_title": "Data Scientist",
            "family_title": "Data and Analytics Professionals",
            "job_description": "Apply data science techniques to solve business problems",
            "riasec_code": "ICA",
            "primary_interest_cluster": "Technology and Innovation",
            "aptitude_scores": {"Numerical": 90, "Digital/Computer": 88},
            "primary_skills": ["Python", "Machine Learning", "Data Analysis"]
        },
        "expected_field_boost": 0.15,
        "should_match": True
    },
    {
        "name": "Test 6: Field with Common Words (Business and Management)",
        "user_profile": {
            "current_field": "Business and Management",
            "riasec_code": "ECR",
            "interests": ["Business and Entrepreneurship"],
            "aptitude_percentiles": {"Leadership/Persuasion": 87}
        },
        "job": {
            "job_id": "test_006",
            "nco_title": "Business Consultant",
            "family_title": "Management and Business Professionals",
            "job_description": "Provide strategic business advice to organizations",
            "riasec_code": "ECS",
            "primary_interest_cluster": "Business and Entrepreneurship",
            "aptitude_scores": {"Leadership/Persuasion": 82},
            "primary_skills": ["Strategic Planning", "Business Analysis"]
        },
        "expected_field_boost": 0.15,
        "should_match": True
    }
]

# Import the service
try:
    from services.recommendation_service import HierarchicalRecommendationService
    
    print("\n✅ Successfully imported HierarchicalRecommendationService")
    print("\n" + "=" * 80)
    print("RUNNING TESTS")
    print("=" * 80)
    
    # Create service instance
    service = HierarchicalRecommendationService()
    
    # Track results
    passed = 0
    failed = 0
    test_results = []
    
    for i, test in enumerate(test_cases, 1):
        print(f"\n{'=' * 80}")
        print(f"📋 {test['name']}")
        print(f"{'=' * 80}")
        print(f"User Field: {test['user_profile']['current_field']}")
        print(f"Job Title: {test['job']['nco_title']}")
        print(f"Expected Boost: {test['expected_field_boost']} ({int(test['expected_field_boost']*100)}%)")
        print(f"Should Match: {test['should_match']}")
        print("-" * 80)
        
        # Run the scoring
        result = service._score_job_hierarchical(test['user_profile'], test['job'])
        
        # Extract field boost from similarity breakdown
        actual_field_boost = result.get('similarity_breakdown', {}).get('field_boost', 0) / 100.0
        
        print(f"\n📊 RESULTS:")
        print(f"   Match Percentage: {result.get('match_percentage', 0)}%")
        print(f"   Field Boost Applied: {actual_field_boost} ({int(actual_field_boost*100)}%)")
        print(f"   Reasoning: {result.get('reasoning', 'N/A')}")
        
        # Check if test passed
        test_passed = abs(actual_field_boost - test['expected_field_boost']) < 0.01
        
        if test_passed:
            print(f"\n✅ TEST PASSED")
            passed += 1
        else:
            print(f"\n❌ TEST FAILED")
            print(f"   Expected: {test['expected_field_boost']} ({int(test['expected_field_boost']*100)}%)")
            print(f"   Got: {actual_field_boost} ({int(actual_field_boost*100)}%)")
            failed += 1
        
        test_results.append({
            "name": test['name'],
            "passed": test_passed,
            "expected": test['expected_field_boost'],
            "actual": actual_field_boost
        })
    
    # Summary
    print("\n" + "=" * 80)
    print("📊 TEST SUMMARY")
    print("=" * 80)
    print(f"Total Tests: {len(test_cases)}")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"Success Rate: {(passed/len(test_cases)*100):.1f}%")
    
    print("\n" + "=" * 80)
    print("DETAILED RESULTS")
    print("=" * 80)
    for result in test_results:
        status = "✅ PASS" if result['passed'] else "❌ FAIL"
        print(f"{status} - {result['name']}")
        if not result['passed']:
            print(f"     Expected: {result['expected']}, Got: {result['actual']}")
    
    # Check for potential issues
    print("\n" + "=" * 80)
    print("🔍 DIAGNOSTIC CHECKS")
    print("=" * 80)
    
    if failed > 0:
        print("⚠️  Some tests failed. Potential issues:")
        print("   1. Check if logging level is set to DEBUG in production")
        print("   2. Verify job database contains all required fields")
        print("   3. Check for case-sensitivity issues in field matching")
        print("   4. Ensure common words filter isn't too aggressive")
    else:
        print("✅ All tests passed! Field booster is working correctly.")
    
    print("\n" + "=" * 80)
    
    # Return exit code
    sys.exit(0 if failed == 0 else 1)
    
except ImportError as e:
    print(f"\n❌ ERROR: Could not import recommendation service")
    print(f"   {str(e)}")
    print("\n💡 Make sure you're running this from the backend directory:")
    print("   cd backend && python test_field_booster.py")
    sys.exit(1)
except Exception as e:
    print(f"\n❌ ERROR: {str(e)}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
