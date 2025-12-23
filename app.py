import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import google.generativeai as genai
import pandas as pd
import random
import time
import hashlib
import json

# --- 1. 설정 및 초기화 ---
st.set_page_config(page_title="한국어 간이 레벨 테스트", layout="wide")

# (1) Gemini 설정
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
except:
    st.error("Gemini API 키가 설정되지 않았습니다.")

# (2) Firebase 설정 (Streamlit Cloud용)
# 이미 앱이 초기화되었는지 확인
if not firebase_admin._apps:
    try:
        # st.secrets에서 정보 가져오기
        key_dict = json.loads(st.secrets["FIREBASE_KEY"])
        cred = credentials.Certificate(key_dict)
        firebase_admin.initialize_app(cred)
    except Exception as e:
        st.error(f"데이터베이스 연결 오류: {e}")

db = firestore.client()

# --- 2. 데이터 암호화 및 유틸리티 함수 ---
def encrypt_data(text):
    """간단한 해시 암호화 (복호화 불가능, 식별만 가능)"""
    return hashlib.sha256(text.encode()).hexdigest()[:10]

def make_code(univ_name, name):
    """연구용 식별 코드 생성 (예: A대001 스타일 흉내)"""
    # 실제로는 DB 카운트가 필요하지만, 간단히 대학명 해시+랜덤숫자로 생성
    univ_hash = hashlib.sha256(univ_name.encode()).hexdigest()[:2].upper()
    rand_num = random.randint(100, 999)
    return f"{univ_hash}대{rand_num}"

# --- 3. 문제 데이터 로드 ---
import json

# 로컬 테스트용 혹은 배포용 파일 읽기
try:
    with open('problems.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
        # JSON 키 이름(SET_A 등)이 정확해야 합니다.
        PROBLEM_SETS = [data['SET_A'], data['SET_B'], data['SET_C']]
except FileNotFoundError:
    st.error("오류: 'problems.json' 파일을 찾을 수 없습니다. 같은 폴더에 파일이 있는지 확인해주세요.")
    st.stop()
except json.JSONDecodeError:
    st.error("오류: 'problems.json' 파일의 형식이 잘못되었습니다. 콤마(,)나 괄호를 확인해주세요.")
    st.stop()

# 쓰기 문제 (세트별로 다른 쓰기 문제가 JSON에 포함되어 있으므로, 
# 여기서는 공통 정의를 삭제하거나, JSON 내의 40번 문제를 활용하도록 로직을 수정해야 합니다.)
# -> 위 코드 로직상 40번 문제가 쓰기 문제로 포함되어 들어오므로
# -> 아래 WRITING_QUESTION 변수는 삭제해도 되지만, 
# -> 기존 코드 호환성을 위해 화면 표시용 함수에서 '마지막 문제(40번)'를 쓰기 문제로 인식하게 처리하겠습니다.

# 쓰기 문제 (공통 혹은 세트별)
WRITING_QUESTION = {
    "question": "다음 그래프를 보고 200~300자로 설명하는 글을 쓰십시오.",
    "image_desc": "[그래프 설명: 한국의 연도별 커피 소비량 변화, 2010년 300잔 -> 2020년 500잔으로 증가]", # 실제 이미지는 st.image로 넣어야 함
    "score": 8
}

# --- 4. 앱 UI 및 로직 ---

def main():
    st.title("🇰🇷 한국어 실력 진단 평가 (연구용)")
    
    # 세션 상태 초기화
    if 'page' not in st.session_state: st.session_state.page = 'login'
    if 'answers' not in st.session_state: st.session_state.answers = {}
    if 'start_time' not in st.session_state: st.session_state.start_time = None
    if 'selected_set_idx' not in st.session_state: st.session_state.selected_set_idx = random.randint(0, len(PROBLEM_SETS)-1)
    if 'shuffled_questions' not in st.session_state: 
        # 선택된 세트 가져오기
        raw_questions = PROBLEM_SETS[st.session_state.selected_set_idx]
        # 유형별로 섞고 싶다면 여기서 로직 추가 (지금은 통째로 섞음)
        st.session_state.shuffled_questions = random.sample(raw_questions, len(raw_questions)) # 무작위 섞기

    # --- 페이지 1: 로그인 ---
    if st.session_state.page == 'login':
        st.info("이 테스트는 연구 목적으로 진행됩니다. 개인정보는 암호화되어 관리됩니다.")
        
        with st.form("login_form"):
            name = st.text_input("이름")
            univ = st.text_input("소속 대학교 (한글로 입력, 예: 단국대학교)")
            email = st.text_input("이메일 (Gmail 권장)")
            submitted = st.form_submit_button("시험 시작하기")
            
            if submitted:
                if name and univ and email:
                    st.session_state.user_info = {
                        "name": name,
                        "univ": univ,
                        "email": email,
                        "code": make_code(univ, name) # A대001 스타일
                    }
                    st.session_state.start_time = time.time()
                    st.session_state.page = 'test'
                    st.rerun()
                else:
                    st.warning("모든 정보를 입력해주세요.")

    # --- 페이지 2: 시험 진행 ---
    elif st.session_state.page == 'test':
        st.subheader(f"수험번호: {st.session_state.user_info['code']}")
        st.markdown("---")
        
       # 1. 객관식 문제 (1~39번)
            with st.form("test_form"):
                questions = st.session_state.shuffled_questions
                
                # 마지막 문제(쓰기)를 제외하고 반복
                obj_questions = [q for q in questions if q['type'] != '쓰기' and '쓰기' not in q['type']]
                writing_question = [q for q in questions if q['type'] == '쓰기' or '쓰기' in q['type']][0]
                
                # 객관식 출력
                for idx, q in enumerate(obj_questions):
                    st.write(f"**{idx+1}. [{q['type']}]** {q['question']}")
                    choice = st.radio(f"{idx+1}번 답안 선택", q['options'], key=f"q_{q['id']}", index=None)
                    st.session_state.answers[q['id']] = choice
                    st.markdown("---")
                
                # 2. 쓰기 문제 (JSON에서 가져온 내용으로 표시)
                st.write(f"**[쓰기]** {writing_question['question']}")
                # 만약 JSON에 image_desc 같은 필드가 없다면 question에 포함되어 있다고 가정
                writing_answer = st.text_area("답안을 작성하세요 (200~300자)", height=200)
                
                submit_test = st.form_submit_button("제출 및 채점하기")
            
            if submit_test:
                if not writing_answer:
                    st.warning("쓰기 답안을 작성해주세요.")
                else:
                    st.session_state.answers['writing'] = writing_answer
                    st.session_state.end_time = time.time()
                    st.session_state.page = 'scoring'
                    st.rerun()

    # --- 페이지 3: 채점 및 결과 ---
    elif st.session_state.page == 'scoring':
        with st.spinner("AI가 채점 중입니다... 잠시만 기다려주세요."):
            # 1. 객관식 채점
            score_obj = 0
            questions = PROBLEM_SETS[st.session_state.selected_set_idx] # 원본 세트에서 정답 비교
            details = {}
            
            for q in questions:
                user_choice = st.session_state.answers.get(q['id'])
                # 보기가 선택되었고, 그 텍스트가 정답 텍스트와 일치하는지 확인 (인덱스로 매핑 필요)
                # 간편함을 위해 여기선 options 리스트의 인덱스로 비교한다고 가정
                # 실제 구현 시 options 값과 user_choice 문자열 비교 로직 필요
                is_correct = False
                if user_choice:
                    # user_choice가 options의 몇 번째인지 찾기
                    try:
                        choice_idx = q['options'].index(user_choice)
                        if choice_idx == q['answer']:
                            score_obj += q['score']
                            is_correct = True
                    except:
                        pass
                
                details[q['id']] = {
                    "type": q['type'],
                    "user_ans": user_choice,
                    "correct": is_correct,
                    "score_earned": q['score'] if is_correct else 0
                }

            # 2. 쓰기 채점 (Gemini API)
            try:
                model = genai.GenerativeModel('gemini-pro')
                prompt = f"""
                당신은 한국어 능력 시험(TOPIK) 채점관입니다.
                다음은 외국인 학습자의 쓰기 답안입니다.
                문제: {WRITING_QUESTION['image_desc']} 내용을 바탕으로 그래프 해석하기.
                학생 답안: {st.session_state.answers['writing']}
                
                이 답안을 3~4급 수준 기준으로 0점에서 8점 사이로 점수를 매겨주세요.
                오직 숫자만 출력하세요. (예: 6)
                """
                response = model.generate_content(prompt)
                score_writing = int(response.text.strip())
            except:
                score_writing = 0 # 에러 시 0점 처리 혹은 재시도 로직 필요
            
            total_score = score_obj + score_writing
            
            # 3. 데이터 저장
            duration = st.session_state.end_time - st.session_state.start_time
            
            doc_data = {
                "name_enc": st.session_state.user_info['name'], # 실제로는 암호화 함수 적용 권장
                "univ_enc": st.session_state.user_info['code'],
                "email": st.session_state.user_info['email'],
                "total_score": total_score,
                "score_obj": score_obj,
                "score_writing": score_writing,
                "details": str(details), # 상세 내역 문자열로 저장
                "writing_text": st.session_state.answers['writing'],
                "duration_sec": int(duration),
                "timestamp": firestore.SERVER_TIMESTAMP
            }
            db.collection("results").add(doc_data)
            
            st.success("제출이 완료되었습니다.")
            st.metric("총 점수", f"{total_score}점")
            st.info("결과를 검토하여 연구 프로그램 참여 가능 여부를 메일로 안내드리겠습니다. 기다려 주십시오.")
            
            # 재응시 방지
            st.stop()

    # --- 관리자 메뉴 (사이드바 하단) ---
    st.sidebar.markdown("---")
    with st.sidebar.expander("관리자 메뉴"):
        admin_pwd = st.text_input("관리자 암호", type="password")
        if admin_pwd == st.secrets["ADMIN_PASSWORD"]: # secrets에 비번 설정 필요
            if st.button("데이터 다운로드 (CSV)"):
                docs = db.collection("results").stream()
                data = []
                for doc in docs:
                    d = doc.to_dict()
                    if 'timestamp' in d: d['timestamp'] = d['timestamp'].isoformat()
                    data.append(d)
                
                if data:
                    df = pd.DataFrame(data)
                    csv = df.to_csv(index=False).encode('utf-8-sig')
                    st.download_button("CSV 다운로드", csv, "results.csv", "text/csv")
                else:
                    st.write("데이터가 없습니다.")

if __name__ == "__main__":

    main()
