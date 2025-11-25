#!/usr/bin/env python3
"""
DeBERTa AI Filter
"""

import sys
import subprocess
import io
import json
import argparse
import torch
from transformers import DebertaV2Tokenizer, AutoModelForSequenceClassification
from typing import Dict, List, Tuple
import os
import traceback

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# ============================================
# 필수 패키지 자동 설치
# ============================================
def install_requirements():
    """필수 패키지가 없으면 자동 설치"""
    required_packages = {
        'torch': 'torch',
        'transformers': 'transformers',
        'protobuf': 'protobuf',
        'tiktoken': 'tiktoken',
        'sentencepiece': 'sentencepiece'
    }
    
    missing_packages = []
    
    for package_name, pip_name in required_packages.items():
        try:
            __import__(package_name)
        except ImportError:
            missing_packages.append(pip_name)
    
    if missing_packages:
        print("=" * 70)
        print("[Package] Installing missing packages...")
        print("=" * 70)
        
        for package in missing_packages:
            print(f"\n[Install] Installing {package}...")
            try:
                subprocess.check_call([
                    sys.executable, 
                    "-m", 
                    "pip", 
                    "install", 
                    package
                ])
                print(f"[Success] {package} installed successfully!")
            except subprocess.CalledProcessError as e:
                print(f"[Error] Failed to install {package}: {e}")
                sys.exit(1)
        
        print("\n" + "=" * 70)
        print("[Success] All packages installed!")
        print("=" * 70)

install_requirements()


class SecretAIFilter:
    """DeBERTa 기반 시크릿 진위 판별 필터"""
    
    def __init__(self, model_path: str, device: str = 'auto'):
    
        self.model_name = "microsoft/deberta-v3-base"
        
        # Device 설정
        self.device = self._setup_device(device)
        
        print(f"[Model] Loading DeBERTa model from {model_path}...")
        
        # Tokenizer 로드
        self.tokenizer = DebertaV2Tokenizer.from_pretrained(self.model_name)
        
        # 모델 로드
        self.model = AutoModelForSequenceClassification.from_pretrained(
            self.model_name,
            num_labels=2,
            problem_type="single_label_classification"
        )
        
        # 체크포인트 로드
        checkpoint = torch.load(model_path, map_location=self.device)
        self.model.load_state_dict(checkpoint['model_state_dict'])
        self.model.to(self.device)
        self.model.eval()
        
        print(f"[Success] Model loaded on {self.device}")
        
        # GPU 정보 출력
        if self.device.type == 'cuda':
            self._print_gpu_info()
    
    def _setup_device(self, device_arg: str) -> torch.device:
        
        if device_arg == 'auto':
            # 자동 감지
            if torch.cuda.is_available():
                device = torch.device('cuda')
                gpu_name = torch.cuda.get_device_name(0)
                print(f"[GPU] CUDA available: {gpu_name}")
                return device
            else:
                device = torch.device('cpu')
                print(f"[CPU] CUDA not available, using CPU")
                return device
        elif device_arg == 'cuda':
            # GPU 강제
            if torch.cuda.is_available():
                device = torch.device('cuda')
                gpu_name = torch.cuda.get_device_name(0)
                print(f"[GPU] Using CUDA: {gpu_name}")
                return device
            else:
                print(f"[Warning] CUDA not available, falling back to CPU")
                return torch.device('cpu')
        else:
            # CPU 강제
            print(f"[CPU] Using CPU (forced)")
            return torch.device('cpu')
    
    def _print_gpu_info(self):
        """GPU 메모리 정보 출력"""
        if torch.cuda.is_available():
            allocated = torch.cuda.memory_allocated(0) / 1024**3
            reserved = torch.cuda.memory_reserved(0) / 1024**3
            total = torch.cuda.get_device_properties(0).total_memory / 1024**3
            print(f"[GPU Memory] Allocated: {allocated:.2f} GB / Reserved: {reserved:.2f} GB / Total: {total:.2f} GB")
    
    def create_model_input(self, finding: Dict) -> str:
        # Secret 텍스트만 추출
        secret = finding.get('secret_raw', '')
        
        if not secret:
            raise ValueError("Missing 'secret_raw' field")
        
        # Secret만 반환
        return str(secret)
    
    def predict_single(self, finding: Dict, confidence_threshold: float = 0.7) -> Dict:
        """
        단일 finding 예측

        Returns:
            예측 결과 딕셔너리
        """
        try:
            # GPU에서 예측 시도
            return self._predict_on_device(finding, confidence_threshold, self.device)
            
        except RuntimeError as e:
            # GPU OOM 처리
            if 'out of memory' in str(e).lower():
                print(f"\n[Warning] GPU OOM detected, falling back to CPU for this prediction")
                
                # CPU로 재시도
                try:
                    return self._predict_on_device(finding, confidence_threshold, torch.device('cpu'))
                except Exception as cpu_error:
                    raise Exception(f"CPU prediction also failed: {cpu_error}")
            else:
                raise
        except Exception as e:
            raise Exception(f"Error in prediction: {e}")
    
    def _predict_on_device(self, finding: Dict, confidence_threshold: float, device: torch.device) -> Dict:
        """
        특정 Device에서 예측 수행
        
        Args:
            finding: Finding 딕셔너리
            confidence_threshold: Threshold
            device: torch.device
        
        Returns:
            예측 결과
        """
        # Secret만 사용!
        model_input = self.create_model_input(finding)
        
        # Tokenize
        encoding = self.tokenizer(
            model_input,
            truncation=True,
            max_length=128,
            padding='max_length',
            return_tensors='pt'
        )
        
        # Device로 이동
        input_ids = encoding['input_ids'].to(device)
        attention_mask = encoding['attention_mask'].to(device)
        
        # 모델도 임시로 해당 device로
        original_device = self.model.device
        if device != original_device:
            self.model.to(device)
        
        try:
            # 예측
            with torch.no_grad():
                outputs = self.model(input_ids=input_ids, attention_mask=attention_mask)
                logits = outputs.logits
                probs = torch.softmax(logits, dim=1)
                
                # prob_true (Secret 확률)
                prob_false = probs[0][0].item()
                prob_true = probs[0][1].item()
            
            # Threshold 적용
            if prob_true >= confidence_threshold:
                label = 'Y'
                is_false_positive = False
                confidence = prob_true
            else:
                label = 'N'
                is_false_positive = True
                confidence = prob_false
            
            prediction = {
                "label": label,
                "confidence": confidence,
                "is_false_positive": is_false_positive,
                "prob_false": round(prob_false, 4),
                "prob_true": round(prob_true, 4)
            }
            
            return prediction
            
        finally:
            # 원래 device로 복구
            if device != original_device:
                self.model.to(original_device)
    
    def get_device_info(self) -> Dict:
        """
        현재 Device 정보 반환
        
        Returns:
            Device 정보 딕셔너리
        """
        info = {
            'device': str(self.device),
            'cuda_available': torch.cuda.is_available(),
        }
        
        if torch.cuda.is_available():
            info['gpu_name'] = torch.cuda.get_device_name(0)
            info['gpu_memory_allocated'] = f"{torch.cuda.memory_allocated(0) / 1024**3:.2f} GB"
            info['gpu_memory_reserved'] = f"{torch.cuda.memory_reserved(0) / 1024**3:.2f} GB"
            info['gpu_memory_total'] = f"{torch.cuda.get_device_properties(0).total_memory / 1024**3:.2f} GB"
        
        return info



def process_stream(input_file, output_file, model_path, confidence_threshold=0.7, device='auto', verbose=False):
    """스트리밍 방식으로 처리"""
    
    print("=" * 70)
    print("[AI Filter] DeBERTa AI Filter")
    print("=" * 70)
    
    # 파일 크기
    file_size_gb = os.path.getsize(input_file) / (1024**3)
    print(f"\n[Input] File: {input_file}")
    print(f"   Size: {file_size_gb:.2f} GB")
    
    # 모델 로드 (GPU 자동 감지)
    ai_filter = SecretAIFilter(model_path, device)
    
    # Device 정보 출력
    device_info = ai_filter.get_device_info()
    print(f"\n[Device Info]")
    for key, value in device_info.items():
        print(f"   {key}: {value}")
    
    # 통계
    total = 0
    predicted_true = 0
    predicted_false = 0
    errors = 0
    gpu_oom_count = 0
    
    print(f"\n[Process] Processing findings...")
    print(f"   Confidence threshold: {confidence_threshold}")
    print(f"   Verbose mode: {verbose}")
    
    # 출력 파일 준비
    outfile = open(output_file, 'w', encoding='utf-8')
    outfile.write('{"findings":[\n')
    
    try:
        # JSON 로드 (List/Dict 모두 지원)
        with open(input_file, 'r', encoding='utf-8') as infile:
            data = json.load(infile)
            
            if isinstance(data, list):
                # 리스트 형식: [{"secret": ...}, ...]
                findings = data
                print(f"   [Format] Lightweight parser format detected")
            elif isinstance(data, dict):
                # 딕셔너리 형식: {"findings": [...]}
                findings = data.get('findings', [])
                print(f"   [Format] Standard format detected")
            else:
                print("[Error] Unknown JSON format")
                return
            # ==========================================
            
            if not findings:
                print("[Error] No findings found")
                return
            
            print(f"   Found {len(findings)} findings\n")
        
        # findings 처리
        print("[Process] Starting prediction...\n")
        
        for i, finding in enumerate(findings):
            finding_id = i + 1
        
            if 'secret_raw' not in finding and 'secret' in finding:
                finding['secret_raw'] = finding['secret']
            # ==============================================
            
            file_path = finding.get('file_path', 'unknown')
            secret_type = finding.get('secret_type') or finding.get('category', 'Unknown')
            
            # 진행 상황
            if verbose or finding_id % 100 == 0:
                print(f"[{finding_id}/{len(findings)}] Processing...")
                
                # GPU 메모리 체크 (500개마다)
                if finding_id % 500 == 0 and ai_filter.device.type == 'cuda':
                    allocated = torch.cuda.memory_allocated(0) / 1024**3
                    print(f"   GPU Memory: {allocated:.2f} GB allocated")
            
            try:
                # AI 예측
                prediction = ai_filter.predict_single(finding, confidence_threshold)
                
                finding['deberta_prediction'] = prediction
                
                # 상세 로그
                if verbose:
                    print(f"   Prediction: {prediction['label']} "
                          f"(prob_true={prediction['prob_true']:.4f}, "
                          f"prob_false={prediction['prob_false']:.4f})")
                
                # 통계
                total += 1
                if prediction['label'] == 'Y':
                    predicted_true += 1
                else:
                    predicted_false += 1
                
            except Exception as e:
                errors += 1
                error_msg = str(e)
                
                # GPU OOM 카운트
                if 'out of memory' in error_msg.lower():
                    gpu_oom_count += 1
                
                print(f"\n[Error] ERROR at finding {finding_id}:")
                print(f"   File: {file_path}")
                print(f"   Type: {secret_type}")
                print(f"   Error: {error_msg}")
                
                if verbose:
                    traceback.print_exc()
                
                finding['deberta_prediction'] = {
                    "label": "ERROR",
                    "confidence": 0.0,
                    "is_false_positive": None,
                    "prob_false": 0.0,
                    "prob_true": 0.0,
                    "error": error_msg
                }
                
                total += 1
            
            # 파일 쓰기
            if finding_id > 1:
                outfile.write(',\n')
            json.dump(finding, outfile, ensure_ascii=False, indent=2)
        
    finally:
        outfile.write('\n],\n')
        
        summary = {
            "total": total,
            "predicted_true": predicted_true,
            "predicted_false": predicted_false,
            "errors": errors,
            "gpu_oom_count": gpu_oom_count,
            "success_rate": round((total - errors) / total * 100, 2) if total > 0 else 0
        }
        
        outfile.write(f'"summary":{json.dumps(summary, indent=2)}\n')
        outfile.write('}')
        outfile.close()
    
    print(f"\n{'=' * 70}")
    print(f"[Success] Completed!")
    print(f"{'=' * 70}")
    print(f"Total findings: {total}")
    
    if total > 0:
        print(f"  TRUE:  {predicted_true} ({predicted_true/total*100:.1f}%)")
        print(f"  FALSE: {predicted_false} ({predicted_false/total*100:.1f}%)")
        print(f"  ERRORS: {errors} ({errors/total*100:.1f}%)")
        
        if gpu_oom_count > 0:
            print(f"  GPU OOM handled: {gpu_oom_count}")
    
    print(f"\n[Output] File: {output_file}")
    
    # 최종 GPU 메모리 상태
    if device_info['cuda_available']:
        print(f"\n[GPU Final State]")
        print(f"   Allocated: {torch.cuda.memory_allocated(0) / 1024**3:.2f} GB")
        print(f"   Reserved:  {torch.cuda.memory_reserved(0) / 1024**3:.2f} GB")


def main():
    parser = argparse.ArgumentParser(
        description="DeBERTa AI Filter",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Auto-detect GPU (recommended)
  python ai_filter.py -i input.json -m model.pt -o output.json
  
  # Force GPU
  python ai_filter.py -i input.json -m model.pt -d cuda
  
  # Force CPU
  python ai_filter.py -i input.json -m model.pt -d cpu
  
  # With custom threshold
  python ai_filter.py -i input.json -m model.pt -t 0.7
        """
    )
    parser.add_argument('-i', '--input', required=True, help='Input JSON file')
    parser.add_argument('-m', '--model', required=True, help='Model checkpoint path')
    parser.add_argument('-o', '--output', default='predictions.json', help='Output JSON file')
    parser.add_argument('-t', '--confidence-threshold', type=float, default=0.7,
                       help='Confidence threshold (default: 0.7)')
    parser.add_argument('-d', '--device', default='auto', choices=['auto', 'cpu', 'cuda'],
                       help='Device: auto (GPU priority), cuda (GPU only), cpu (CPU only)')
    parser.add_argument('-v', '--verbose', action='store_true',
                       help='Enable verbose output')
    
    args = parser.parse_args()
    
    process_stream(
        args.input,
        args.output,
        args.model,
        args.confidence_threshold,
        args.device,
        args.verbose
    )


if __name__ == "__main__":
    main()