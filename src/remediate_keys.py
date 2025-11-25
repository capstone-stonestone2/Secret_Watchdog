# src/remediate_keys.py

import argparse
import json
import boto3
from botocore.exceptions import ClientError

# Boto3 IAM 클라이언트 전역 생성
iam_client = boto3.client('iam')

def find_user_for_key(access_key_id: str) -> str | None:
    """
    주어진 Access Key ID를 소유한 IAM 사용자의 이름을 찾습니다.
    Boto3에는 Access Key ID로 사용자를 직접 찾는 기능이 없으므로,
    모든 사용자의 키를 스캔하여 일치하는 것을 찾아야 합니다.

    :param access_key_id: 찾고자 하는 AWS Access Key ID
    :return: 해당 키를 소유한 사용자의 이름 (UserName). 없으면 None.
    """
    print(f"Finding user for Access Key ID: {access_key_id}...")
    try:
        # Paginator를 사용하여 계정에 사용자가 많아도 모두 조회
        paginator = iam_client.get_paginator('list_users')
        for page in paginator.paginate():
            for user in page['Users']:
                user_name = user['UserName']
                
                # 각 사용자의 Access Key 목록을 조회
                keys_paginator = iam_client.get_paginator('list_access_keys')
                for keys_page in keys_paginator.paginate(UserName=user_name):
                    for key_metadata in keys_page['AccessKeyMetadata']:
                        if key_metadata['AccessKeyId'] == access_key_id:
                            print(f" Found owner! User: {user_name}")
                            return user_name
                            
    except ClientError as e:
        print(f" AWS API Error while finding user: {e}")
        return None

    print(f" User for key {access_key_id} not found.")
    return None

def remediate_aws_key(access_key_id: str, file_path: str = "unknown", line_num: int = 0, confidence: float = 0.0) -> dict:
    """
    특정 Access Key를 찾아 비활성화(Inactive)
    
    :return: 처리 결과를 담은 dict
    """
    print("-" * 30)
    print(f" Starting remediation for key: {access_key_id}")
    
    result = {
        "access_key_id": access_key_id,
        "file_path": file_path,
        "line": line_num,
        "confidence": confidence,
        "user_name": None,
        "status": "failed",
        "message": ""
    }
    
    # 1. 키의 소유자(사용자 이름) 찾기
    user_name = find_user_for_key(access_key_id)
    
    if not user_name:
        print("-> Remediation skipped: Could not determine key's owner.")
        result["message"] = "Could not determine key's owner"
        print("-" * 30)
        return result

    result["user_name"] = user_name

    # 2. 키 비활성화 실행
    try:
        iam_client.update_access_key(
            UserName=user_name,
            AccessKeyId=access_key_id,
            Status='Inactive'
        )
        print(f" SUCCESS: Access key {access_key_id} for user '{user_name}' has been deactivated.")
        result["status"] = "deactivated"
        result["message"] = f"Successfully deactivated key for user '{user_name}'"
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchEntity':
            print(f"-> INFO: Key {access_key_id} or user {user_name} no longer exists. No action needed.")
            result["status"] = "not_found"
            result["message"] = "Key or user no longer exists"
        else:
            print(f" FAILED to deactivate key {access_key_id}. Error: {e}")
            result["message"] = f"Failed to deactivate: {str(e)}"
    print("-" * 30)
    
    return result


def main():
    """
    메인 실행 함수
    """
    parser = argparse.ArgumentParser(description="Auto-remediate leaked AWS keys found by TruffleHog or AI-filtered results.")
    parser.add_argument('--results-file', required=True, help="Path to the results JSON file (TruffleHog or AI-filtered).")
    parser.add_argument('--mode', choices=['standard', 'ai-filtered'], default='standard', 
                       help="Mode: 'standard' for TruffleHog raw, 'ai-filtered' for AI predictions (default: standard)")
    parser.add_argument('--output', default='outputs/remediation_results.json',
                       help="Path to save remediation results JSON (default: outputs/remediation_results.json)")
    args = parser.parse_args()

    # 최종 결과 구조
    remediation_results = {
        "aws_keys": [],
        "general_secrets": []
    }

    try:
        with open(args.results_file, 'r') as f:
            data = json.load(f)
        
        # ============================================
        # 데이터 형식 처리
        # ============================================
        
        if args.mode == 'ai-filtered':
            # AI 필터링 결과 형식: {"findings": [...]}
            print(" Processing AI-filtered results...")
            findings = data.get('findings', [])
            
            if not findings:
                print("No findings in AI-filtered results. Nothing to do.")
                # 빈 결과라도 저장
                with open(args.output, 'w') as f:
                    json.dump(remediation_results, f, indent=2)
                return
                
            print(f"Found {len(findings)} AI-filtered findings.")
            
            # AI가 TRUE로 확인한 결과 처리
            for finding in findings:
                # AI 예측 확인
                prediction = finding.get('deberta_prediction', {})
                if prediction.get('label') != 'Y':
                    continue
                
                # secret_type 또는 category 사용 (null-safe)
                secret_type = finding.get('secret_type', '') or finding.get('category', 'Unknown')
                secret_raw = finding.get('secret_raw', '')
                file_path = finding.get('file_path', 'unknown')
                line_num = finding.get('line', 0) or finding.get('line_number', 0)  # line과 line_number 모두 지원
                confidence = prediction.get('confidence', 0.0)
                
                # AWS 키인지 확인
                if 'AWS' in secret_type or 'Amazon' in secret_type:
                    if secret_raw and secret_raw.startswith("AKIA"):
                        print(f"\n AI confirmed AWS key (confidence: {confidence:.2%})")
                        print(f"   File: {file_path}")
                        
                        # AWS 키 비활성화 실행
                        result = remediate_aws_key(secret_raw, file_path, line_num, confidence)
                        remediation_results["aws_keys"].append(result)
                else:
                    # 일반 시크릿 정보 수집
                    print(f"\n Detected general secret: {secret_type}")
                    print(f"   File: {file_path}")
                    
                    general_secret_info = {
                        "secret_type": secret_type,
                        "file_path": file_path,
                        "line": line_num,
                        "confidence": confidence,
                        "secret_preview": secret_raw[:20] + "..." if len(secret_raw) > 20 else secret_raw
                    }
                    remediation_results["general_secrets"].append(general_secret_info)
            
            # 결과 요약 출력
            print("\n" + "=" * 50)
            print(" REMEDIATION SUMMARY")
            print("=" * 50)
            print(f" AWS Keys processed: {len(remediation_results['aws_keys'])}")
            print(f"   - Deactivated: {sum(1 for k in remediation_results['aws_keys'] if k['status'] == 'deactivated')}")
            print(f"   - Failed: {sum(1 for k in remediation_results['aws_keys'] if k['status'] == 'failed')}")
            print(f"   - Not found: {sum(1 for k in remediation_results['aws_keys'] if k['status'] == 'not_found')}")
            print(f" General Secrets detected: {len(remediation_results['general_secrets'])}")
            print("=" * 50)
                
        else:
            # 기존 TruffleHog 형식
            print(" Processing TruffleHog raw results...")
            findings = data
            
            # 만약 결과가 list가 아닌 단일 dict 형태라면 list로 감싸줍니다.
            if isinstance(findings, dict):
                findings = [findings]

            if not findings:
                print("No findings in the results file. Nothing to do.")
                # 빈 결과라도 저장
                with open(args.output, 'w') as f:
                    json.dump(remediation_results, f, indent=2)
                return

            print(f"Found {len(findings)} potential leaks in '{args.results_file}'.")

            # 모든 탐지 결과에 대해 자동 대응 실행
            for finding in findings:
                detector_name = finding.get("DetectorName", "")
                leaked_key = finding.get("Raw", "")
                
                # 파일 정보 추출
                source_metadata = finding.get("SourceMetadata", {})
                file_info = source_metadata.get("Data", {}).get("Filesystem", {})
                file_path = file_info.get("file", "unknown")
                line_num = file_info.get("line", 0)
                
                # AWS Access Key ID 패턴을 가진 탐지 결과만 처리
                if detector_name == "AWS":
                    if leaked_key and leaked_key.startswith("AKIA"):
                        result = remediate_aws_key(leaked_key, file_path, line_num)
                        remediation_results["aws_keys"].append(result)
                    else:
                        print(f"Skipping a finding, not a valid AWS Access Key ID: {leaked_key}")
                else:
                    # 일반 시크릿으로 분류
                    if leaked_key:
                        print(f"Detected general secret from detector '{detector_name}'.")
                        general_secret_info = {
                            "secret_type": detector_name,
                            "file_path": file_path,
                            "line": line_num,
                            "confidence": 1.0,  # TruffleHog raw는 confidence 없음
                            "secret_preview": leaked_key[:20] + "..." if len(leaked_key) > 20 else leaked_key
                        }
                        remediation_results["general_secrets"].append(general_secret_info)

            # 결과 요약 출력
            print("\n" + "=" * 50)
            print(" REMEDIATION SUMMARY")
            print("=" * 50)
            print(f" AWS Keys processed: {len(remediation_results['aws_keys'])}")
            print(f"   - Deactivated: {sum(1 for k in remediation_results['aws_keys'] if k['status'] == 'deactivated')}")
            print(f"   - Failed: {sum(1 for k in remediation_results['aws_keys'] if k['status'] == 'failed')}")
            print(f"   - Not found: {sum(1 for k in remediation_results['aws_keys'] if k['status'] == 'not_found')}")
            print(f" General Secrets detected: {len(remediation_results['general_secrets'])}")
            print("=" * 50)

        # 결과를 JSON 파일로 저장
        with open(args.output, 'w') as f:
            json.dump(remediation_results, f, indent=2)
        
        print(f"\n Remediation results saved to: {args.output}")

    except FileNotFoundError:
        print(f"Error: The file '{args.results_file}' was not found.")
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from '{args.results_file}'. Is it empty or corrupt?")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    main()