# parser.py
import json
import os
from pathlib import Path
from typing import Dict, List, Optional


class LightweightParser:
    """
    TruffleHog 파서
    """
    
    def __init__(self):
        """간단한 초기화"""
        pass
    
    def parse(self, result_json_path: str, output_path: str = "parsed_results.json"):
        """
        TruffleHog results.json을 간단하게 파싱
        
        Args:
            result_json_path: TruffleHog 결과 파일
            output_path: 출력 파일
        
        Returns:
            파싱된 결과 리스트
        """
        findings = []
        
        print(f"[Reading] {result_json_path}")
        
        with open(result_json_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                
                try:
                    raw_finding = json.loads(line)
                    parsed = self._parse_finding(raw_finding)
                    if parsed:
                        findings.append(parsed)
                except Exception as e:
                    continue
        
        print(f"[Success] Parsed {len(findings)} findings")
        
        # 저장
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(findings, f, indent=2, ensure_ascii=False)
        
        print(f"[Saved] {output_path}")
        
        return findings
    
    def _parse_finding(self, raw: Dict) -> Optional[Dict]:
        """
        핵심 정보만 추출
        
        필수:
        - secret: DeBERTa 입력
        - category: 분석용
        """
        try:
            # 필수: Secret
            secret = raw.get("Raw", "")
            if not secret:
                return None
            
            # 필수: Category (DetectorName)
            category = raw.get("DetectorName", "Unknown")
            
            # 선택: 파일 정보
            metadata = raw.get("SourceMetadata", {}).get("Data", {}).get("Filesystem", {})
            file_path = metadata.get("file", "")
            line = metadata.get("line", 0)
            
            # 간단한 결과
            return {
                "secret": secret,
                "category": category,
                "file_path": file_path,
                "line": line
            }
            
        except Exception:
            return None
    
    def get_statistics(self, findings: List[Dict]) -> Dict:
        """
        Category별 통계 생성
        
        Returns:
            통계 딕셔너리
        """
        from collections import Counter
        
        total = len(findings)
        categories = Counter(f['category'] for f in findings)
        
        stats = {
            "total": total,
            "by_category": dict(categories),
            "unique_categories": len(categories)
        }
        
        return stats
    
    def filter_by_category(self, findings: List[Dict], category: str) -> List[Dict]:
        """
        특정 Category만 필터링
        
        Returns:
            필터링된 결과
        """
        return [f for f in findings if f['category'] == category]


def main():
    """사용 예제"""
    import argparse
    
    DEFAULT_INPUT = "/c/users/songh/desktop/project3/results.json"
    DEFAULT_OUTPUT = "/c/users/songh/desktop/project3/parsed_results.json"
    
    parser = argparse.ArgumentParser(
        description="TruffleHog Parser",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Use default paths
  python parser.py
  
  # Custom input path
  python parser.py custom_results.json
  
  # Custom input and output
  python parser.py input.json -o output.json
  
  # Show statistics
  python parser.py --stats
        """
    )
    
    parser.add_argument("input", 
                       nargs='?',  # 선택적 인자
                       default=DEFAULT_INPUT,
                       help=f"TruffleHog results.json (default: {DEFAULT_INPUT})")
    parser.add_argument("-o", "--output", 
                       default=DEFAULT_OUTPUT, 
                       help=f"Output file (default: {DEFAULT_OUTPUT})")
    parser.add_argument("--stats", action="store_true", help="Show statistics")
    
    args = parser.parse_args()
    
    # 파싱
    p = LightweightParser()
    findings = p.parse(args.input, args.output)
    
    # 통계 출력
    if args.stats:
        stats = p.get_statistics(findings)
        print("\n[Statistics]")
        print(f"Total: {stats['total']}")
        print(f"Categories: {stats['unique_categories']}")
        print("\nBy Category:")
        for cat, count in sorted(stats['by_category'].items(), key=lambda x: -x[1]):
            print(f"  {cat}: {count}")


if __name__ == "__main__":
    main()