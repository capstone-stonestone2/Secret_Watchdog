import os
import json
import argparse
import requests
import re

def get_github_context():
    """GitHub Actions 환경변수에서 컨텍스트 정보를 추출합니다."""
    server_url = os.environ.get("GITHUB_SERVER_URL", "")
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    actor = os.environ.get("GITHUB_ACTOR", "N/A")
    sha = os.environ.get("GITHUB_SHA", "")

    run_url = f"{server_url}/{repository}/actions/runs/{run_id}" if all([server_url, repository, run_id]) else None
    commit_url = f"{server_url}/{repository}/commit/{sha}" if all([server_url, repository, sha]) else None
    
    return {
        "run_url": run_url,
        "commit_url": commit_url,
        "actor": actor
    }

def parse_report_file(report_path: str) -> dict:
    """report.txt 파일을 파싱하여 메트릭 추출"""
    metrics = {
        'tp': 0, 'tn': 0, 'fp': 0, 'fn': 0,
        'precision': 0.0, 'recall': 0.0, 'f1_score': 0.0,
        'accuracy': 0.0, 'fpr': 0.0,
        'total': 0, 'original_fp': 0, 'fp_reduction': 0.0
    }
    
    try:
        with open(report_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # TP, FN, FP, TN 추출
        tp_match = re.search(r'Actual TRUE\s+(\d+)\s+(\d+)', content)
        if tp_match:
            metrics['tp'] = int(tp_match.group(1))
            metrics['fn'] = int(tp_match.group(2))
        
        fp_match = re.search(r'Actual FALSE\s+(\d+)\s+(\d+)', content)
        if fp_match:
            metrics['fp'] = int(fp_match.group(1))
            metrics['tn'] = int(fp_match.group(2))
        
        # 성능 지표 파싱
        precision_match = re.search(r'Precision:\s+([\d.]+)', content)
        if precision_match:
            metrics['precision'] = float(precision_match.group(1))
        
        recall_match = re.search(r'Recall:\s+([\d.]+)', content)
        if recall_match:
            metrics['recall'] = float(recall_match.group(1))
        
        f1_match = re.search(r'F1-Score:\s+([\d.]+)', content)
        if f1_match:
            metrics['f1_score'] = float(f1_match.group(1))
        
        accuracy_match = re.search(r'Accuracy:\s+([\d.]+)', content)
        if accuracy_match:
            metrics['accuracy'] = float(accuracy_match.group(1))
        
        fpr_match = re.search(r'False Positive Rate:\s+([\d.]+)', content)
        if fpr_match:
            metrics['fpr'] = float(fpr_match.group(1))
        
        # 통계 파싱
        total_match = re.search(r'Total Findings:\s+(\d+)', content)
        if total_match:
            metrics['total'] = int(total_match.group(1))
        
        original_fp_match = re.search(r'Original FP count:\s+(\d+)', content)
        if original_fp_match:
            metrics['original_fp'] = int(original_fp_match.group(1))
        
        reduction_match = re.search(r'Reduction:\s+([\d.]+)%', content)
        if reduction_match:
            metrics['fp_reduction'] = float(reduction_match.group(1))
        
    except Exception as e:
        print(f"Warning: report.txt 파싱 중 오류: {e}")
    
    return metrics

def build_performance_report_message(report_path: str, context: dict) -> dict:
    """성능 분석 결과(report.txt)를 Slack 메시지로 생성합니다."""
    
    # report.txt 파싱
    metrics = parse_report_file(report_path)
    
    # 메시지 블록 생성
    message_blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "TruffleHog 오탐율 분석 완료"}
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*AI 필터가 오탐을 {metrics['fp_reduction']:.1f}% 감소시켰습니다*"
            }
        },
        {"type": "divider"},
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Confusion Matrix*\n```TP: {metrics['tp']}  FN: {metrics['fn']}\nFP: {metrics['fp']}  TN: {metrics['tn']}```"},
                {"type": "mrkdwn", "text": f"*F1-Score*\n`{metrics['f1_score']:.2%}`"}
            ]
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Precision*\n`{metrics['precision']:.2%}`"},
                {"type": "mrkdwn", "text": f"*Recall*\n`{metrics['recall']:.2%}`"}
            ]
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Accuracy*\n`{metrics['accuracy']:.2%}`"},
                {"type": "mrkdwn", "text": f"*FP Rate*\n`{metrics['fpr']:.2%}`"}
            ]
        },
        {"type": "divider"},
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*전체 Findings*\n{metrics['total']}개"},
                {"type": "mrkdwn", "text": f"*진짜 탐지 (TP)*\n{metrics['tp']}개"}
            ]
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*오탐 제거 (TN)*\n{metrics['tn']}개"},
                {"type": "mrkdwn", "text": f"*남은 오탐 (FP)*\n{metrics['fp']}개"}
            ]
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*오탐 개선 효과*\n• Before: {metrics['original_fp']}개 오탐\n• After: {metrics['fp']}개 오탐\n• 감소율: {metrics['fp_reduction']:.1f}%"
            }
        }
    ]

    # GitHub Actions 링크 추가
    if context["run_url"]:
        message_blocks.append({
            "type": "actions",
            "elements": [{
                "type": "button",
                "text": {"type": "plain_text", "text": "상세 결과 확인"},
                "url": context["run_url"],
                "style": "primary"
            }]
        })
    
    return {"blocks": message_blocks}

def build_multi_secret_incident_message(remediation_data: dict, context: dict) -> dict:
    """
    다중 시크릿 탐지 및 자동 대응 결과를 Slack 메시지로 생성합니다.
    remediation_results.json 형식을 입력으로 받습니다.
    """
    aws_keys = remediation_data.get("aws_keys", [])
    general_secrets = remediation_data.get("general_secrets", [])
    
    # 메시지 블록 시작
    message_blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "민감 정보 유출 탐지 및 자동 대응 완료"}
        }
    ]
    
    # 요약 섹션
    total_secrets = len(aws_keys) + len(general_secrets)
    deactivated_count = sum(1 for key in aws_keys if key.get("status") == "deactivated")
    
    summary_text = f"*총 {total_secrets}개의 민감 정보가 탐지되었습니다*\n"
    if aws_keys:
        summary_text += f"• AWS 키: {len(aws_keys)}개 (비활성화: {deactivated_count}개)\n"
    if general_secrets:
        summary_text += f"• 일반 시크릿: {len(general_secrets)}개\n"
    summary_text += f"• Commit 작성자: {context['actor']}"
    
    message_blocks.append({
        "type": "section",
        "text": {"type": "mrkdwn", "text": summary_text}
    })
    
    message_blocks.append({"type": "divider"})
    
    # AWS 키 섹션
    if aws_keys:
        message_blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*AWS Access Keys (자동 비활성화)*"}
        })
        
        for idx, key_info in enumerate(aws_keys, 1):
            status_emoji = {
                "deactivated": "[완료]",
                "failed": "[실패]",
                "not_found": "[미발견]"
            }.get(key_info.get("status", "failed"), "[?]")
            
            key_text = (
                f"*#{idx}* {status_emoji}\n"
                f"• 키 ID: `{key_info.get('access_key_id', 'N/A')}`\n"
                f"• 소유자: {key_info.get('user_name', 'Unknown')}\n"
                f"• 위치: {key_info.get('file_path', 'unknown')} (Line {key_info.get('line', 0)})\n"
                f"• 상태: {key_info.get('message', 'No message')}\n"
                f"• 신뢰도: {key_info.get('confidence', 0):.1%}"
            )
            
            message_blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": key_text}
            })
        
        message_blocks.append({"type": "divider"})
    
    # 일반 시크릿 섹션
    if general_secrets:
        message_blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*일반 시크릿 탐지 (수동 확인 필요)*"}
        })
        
        for idx, secret_info in enumerate(general_secrets, 1):
            secret_text = (
                f"*#{idx}*\n"
                f"• 유형: {secret_info.get('secret_type', 'Unknown')}\n"
                f"• 위치: {secret_info.get('file_path', 'unknown')} (Line {secret_info.get('line', 0)})\n"
                f"• 미리보기: `{secret_info.get('secret_preview', 'N/A')}`\n"
                f"• 신뢰도: {secret_info.get('confidence', 0):.1%}"
            )
            
            message_blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": secret_text}
            })
        
        message_blocks.append({"type": "divider"})
    
    # 액션 버튼
    action_elements = []
    
    if context["commit_url"]:
        action_elements.append({
            "type": "button",
            "text": {"type": "plain_text", "text": "문제 커밋 확인"},
            "url": context["commit_url"],
            "style": "danger"
        })
    
    if context["run_url"]:
        action_elements.append({
            "type": "button",
            "text": {"type": "plain_text", "text": "상세 로그 보기"},
            "url": context["run_url"]
        })
    
    if action_elements:
        message_blocks.append({
            "type": "actions",
            "elements": action_elements
        })
    
    return {"blocks": message_blocks}


def send_slack_message(payload: dict):
    """생성된 메시지 페이로드를 Slack으로 전송합니다."""
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook_url:
        print("오류: SLACK_WEBHOOK_URL 환경변수가 설정되지 않았습니다.")
        return

    response = requests.post(
        webhook_url, data=json.dumps(payload),
        headers={'Content-Type': 'application/json'}
    )

    if response.status_code == 200:
        print("Slack 알림을 성공적으로 전송했습니다")
    else:
        print(f"Slack 알림 전송 실패. 상태 코드: {response.status_code}, 응답: {response.text}")


def main():
    parser = argparse.ArgumentParser(description="Send notifications to Slack based on workflow mode.")
    parser.add_argument('--mode', type=str, required=True, choices=['performance', 'incident'],
                        help="The mode of operation: 'performance' for test reports, 'incident' for security alerts.")
    parser.add_argument('--results-file', type=str, required=True,
                        help="Path to the results file (report.txt for performance, remediation_results.json for incident).")
    args = parser.parse_args()

    context = get_github_context()
    slack_payload = None

    if args.mode == 'performance':
        if not os.path.exists(args.results_file):
            print(f"오류: 리포트 파일을 찾을 수 없습니다. 경로: '{args.results_file}'")
            return
        
        slack_payload = build_performance_report_message(args.results_file, context)
    
    elif args.mode == 'incident':
        # remediation_results.json 파일 파싱
        try:
            with open(args.results_file, 'r', encoding='utf-8') as f:
                remediation_data = json.load(f)
            
            # 데이터 검증
            if not remediation_data.get("aws_keys") and not remediation_data.get("general_secrets"):
                print("탐지된 시크릿이 없어 Slack 알림을 보내지 않습니다.")
                return
            
            print(f"AWS 키 {len(remediation_data.get('aws_keys', []))}개, 일반 시크릿 {len(remediation_data.get('general_secrets', []))}개 발견")
            slack_payload = build_multi_secret_incident_message(remediation_data, context)
            
        except FileNotFoundError:
            print(f"파일을 찾을 수 없습니다: {args.results_file}")
            return
        except json.JSONDecodeError as e:
            print(f"JSON 파싱 실패: {e}")
            return
        except Exception as e:
            print(f"오류 발생: {e}")
            return
            
    if slack_payload:
        send_slack_message(slack_payload)

if __name__ == "__main__":
    main()