#!/bin/bash

# ==============================================================================
# [Secret-Watchdog] 자동 설치 스크립트
# ==============================================================================

# 색상 변수 설정
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}[INFO] Secret-Watchdog 설치를 시작합니다...${NC}"

# 1. Git 저장소 루트인지 확인
if [ ! -d ".git" ]; then
    echo -e "${RED}[ERROR] 현재 위치가 Git 저장소가 아닙니다.${NC}"
    echo "프로젝트의 최상위 폴더(Root)에서 이 스크립트를 실행해주세요."
    exit 1
fi

# 2. 보안 시스템(security-system) 클론
REPO_URL="https://github.com/capstone-stonestone2/capstone-2025-2-security.git"
TARGET_DIR="security-system"

echo -e "\n${GREEN}[Step 1] 보안 시스템 다운로드 중...${NC}"

if [ -d "$TARGET_DIR" ]; then
    echo -e "${YELLOW}[WARNING] '$TARGET_DIR' 폴더가 이미 존재합니다.${NC}"
    read -p "기존 폴더를 삭제하고 새로 설치하시겠습니까? (y/n): " confirm
    if [[ "$confirm" == "y" || "$confirm" == "Y" ]]; then
        rm -rf "$TARGET_DIR"
        git clone "$REPO_URL" "$TARGET_DIR"
    else
        echo "기존 폴더를 유지합니다."
    fi
else
    git clone "$REPO_URL" "$TARGET_DIR"
fi

if [ ! -d "$TARGET_DIR" ]; then
    echo -e "${RED}[ERROR] 다운로드 실패. 네트워크 상태를 확인해주세요.${NC}"
    exit 1
fi

# 3. GitHub Actions 워크플로우 설정
echo -e "\n${GREEN}[Step 2] GitHub Actions 워크플로우 설정...${NC}"
WORKFLOW_DIR=".github/workflows"
WORKFLOW_FILE="security_pipeline.yml"

mkdir -p "$WORKFLOW_DIR"

if [ -f "$TARGET_DIR/.github/workflows/$WORKFLOW_FILE" ]; then
    cp "$TARGET_DIR/.github/workflows/$WORKFLOW_FILE" "$WORKFLOW_DIR/"
    echo -e "[SUCCESS] 워크플로우 파일이 복사되었습니다: $WORKFLOW_DIR/$WORKFLOW_FILE"
else
    echo -e "${RED}[ERROR] 원본 워크플로우 파일을 찾을 수 없습니다.${NC}"
    exit 1
fi

# 4. 불필요한 .git 폴더 제거
rm -rf "$TARGET_DIR/.git"

# 5. Git Staging & Commit
echo -e "\n${GREEN}[Step 3] Git 변경 사항 적용...${NC}"
echo -e "${YELLOW}설치된 파일들을 Staging Area에 추가합니다.${NC}"

git add "$TARGET_DIR/" "$WORKFLOW_DIR/$WORKFLOW_FILE"

echo -e "파일들이 git add 되었습니다."
read -p "지금 바로 커밋(Commit) 하시겠습니까? (y/n): " commit_confirm

if [[ "$commit_confirm" == "y" || "$commit_confirm" == "Y" ]]; then
    git commit -m "Add AI-powered secret detection and response system (Secret-Watchdog)"
    echo -e "[SUCCESS] 커밋 완료."
    
    read -p "GitHub 원격 저장소로 푸시(Push) 하시겠습니까? (y/n): " push_confirm
    if [[ "$push_confirm" == "y" || "$push_confirm" == "Y" ]]; then
        current_branch=$(git branch --show-current)
        git push origin "$current_branch"
        echo -e "[SUCCESS] 푸시 완료. GitHub Actions 탭을 확인하세요."
    else
        echo "푸시는 건너뛰었습니다. 나중에 'git push'를 실행해주세요."
    fi
else
    echo "커밋을 건너뛰었습니다. 나중에 'git commit'을 실행해주세요."
fi

# 6. 마무리 안내
echo -e "\n${BLUE}======================================================${NC}"
echo -e "${GREEN}[INFO] 설치가 완료되었습니다.${NC}"
echo -e "${BLUE}======================================================${NC}"
echo -e "\n[중요] GitHub Repository Settings에서 다음 Secrets를 등록해주세요."
echo -e "경로: Settings > Secrets and variables > Actions > New repository secret"
echo -e "--------------------------------------------------------"
echo -e " 1. ${YELLOW}SLACK_WEBHOOK_URL${NC}     (필수)"
echo -e " 2. ${YELLOW}AWS_ACCESS_KEY_ID${NC}     (선택)"
echo -e " 3. ${YELLOW}AWS_SECRET_ACCESS_KEY${NC} (선택)"
echo -e "--------------------------------------------------------"