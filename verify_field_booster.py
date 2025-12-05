#!/usr/bin/env python3
"""
Quick Field Booster Verification Script
Tests the ACTUAL backend/services/recommendation_service.py implementation
"""

import sys
import os

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.recommendation_service import HierarchicalRecommendationService

print("="*80)
print("✅ FIELD BOOSTER QUICK VERIFICATION")
print("="*80)

# Create test cases
test_cases = [
    {
        "name": "Healthcare → Healthcare Administrator",
        "user": {"current_field": "Healthcare", "riasec_code": "SAI", "interests": ["Healthcare and Wellness"], "aptitude_percentiles": {}},
        "job": {"job_id": "001", "nco_title": "Healthcare Administrator", "family_title": "Healthcare Management", 
                "job_description": "Manage healthcare facilities", "riasec_code": "SAI", "primary_interest_cluster": "Healthcare and Wellness",
                "aptitude_scores": {}, "primary_skills": []},
        "expected_bonus": 15
    },
    {
        "name": "Data Science → Data Scientist",
        "user": {"current_field": "Data Science", "riasec_code": "ICA", "interests": ["Technology and Innovation"], "aptitude_percentiles": {}},
        "job": {"job_id": "002", "nco_title": "Data Scientist", "family_title": "Data Analytics",
                "job_description": "Analyze data using ML", "riasec_code": "ICA", "primary_interest_cluster": "Technology and Innovation",
                "aptitude_scores": {}, "primary_skills": ["Python", "Machine Learning"]},
        "expected_bonus": 15
    },
    {
        "name": "Marketing → Civil Engineer (No Match)",
        "user": {"current_field": "Marketing", "riasec_code": "EAS", "interests": ["Business"], "aptitude_percentiles": {}},
        "job": {"job_id": "003", "nco_title": "Civil Engineer", "family_title": "Engineering",
                "job_description": "Design structures", "riasec_code": "RIC", "primary_interest_cluster": "Engineering",
                "aptitude_scores": {}, "primary_skills": ["CAD"]},
        "expected_bonus": 0
    }
]

service = HierarchicalRecommendationService()
print(f"\n✅ Service loaded successfully\n")

passed = 0
failed = 0

for test in test_cases:
    result = service._score_job_hierarchical(test["user"], test["job"])
    actual_bonus = result.get("field_bonus", 0)
    
    print(f"Test: {test['name']}")
    print(f"   Expected Bonus: {test['expected_bonus']}")
    print(f"   Actual Bonus: {actual_bonus}")
    print(f"   Match %: {result['match_percentage']}%")
    print(f"   Reasoning: {result['reasoning']}")
    
    if actual_bonus == test['expected_bonus']:
        print(f"   ✅ PASS\n")
        passed += 1
    else:
        print(f"   ❌ FAIL\n")
        failed += 1

print("="*80)
print(f"Results: {passed} passed, {failed} failed")
print("="*80)

if failed == 0:
    print("\n🎉 All tests passed! Field booster is working correctly.\n")
else:
    print(f"\n⚠️  {failed} test(s) failed. Check implementation.\n")
