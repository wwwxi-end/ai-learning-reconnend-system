import os
import re

def search_queries(path):
    for root, dirs, files in os.walk(path):
        for file in files:
            if not file.endswith('.py'):
                continue
            if 'venv' in root:
                continue
            
            file_path = os.path.join(root, file)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                    matches = re.findall(r'LearningRecord\.query.*filter.*quiz_score', content, re.DOTALL)
                    if matches:
                        print(f"\n{'='*60}")
                        print(f"File: {file_path}")
                        print(f"{'='*60}")
                        for match in matches:
                            print(match.strip())
                            print('---')
                            
                    matches2 = re.findall(r'LearningRecord\.quiz_score\s*(?:!=|==|is_not)\s*None', content)
                    if matches2:
                        print(f"\n{'='*60}")
                        print(f"File: {file_path}")
                        print(f"{'='*60}")
                        for match in matches2:
                            print(f"Found: {match}")
                            
            except Exception as e:
                print(f"Error reading {file_path}: {e}")

search_queries(os.path.dirname(os.path.abspath(__file__)))
