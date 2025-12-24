st.markdown("""
<style>
u {
    text-decoration: none;
    border-bottom: 2px solid red;  /* 빨간색 밑줄 (원하는 색으로 변경 가능) */
    padding-bottom: 2px;
    font-weight: bold;
}
</style>
""", unsafe_allow_html=True)
import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import google.generativeai as genai
import pandas as pd
import random
import time
import hashlib
import json
import os
import streamlit as st

# CSS를 사용하여 UI 요소 숨기기
hide_streamlit_style = """
<style>
    /* 1. 우측 하단 'Manage app' 버튼 숨기기 */
    .stAppDeployButton {
        display: none;
    }

    /* 2. 하단 'Made with Streamlit' 푸터 숨기기 */
    footer {
        visibility: hidden;
    }

    /* 3. (선택사항) 우측 상단 햄버거 메뉴(...) 숨기기 */
    /* 필요 없으면 이 부분은 지우세요 */
    #MainMenu {
        visibility: hidden;
    }
</style>
"""

# HTML/CSS 적용
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# --- 1. 설정 및 초기화 ---
st.set_page_config(page_title="한국어 간이 레벨 테스트", layout="wide")

# (1) Gemini 설정
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
except Exception as e:
    st.error(f"Gemini API 설정 오류: {e}")

# (2) Firebase 설정
if not firebase_admin._apps:
    try:
        # st.secrets에서 가져온 정보는 이미 딕셔너리 형태이므로 json.loads가 필요 없습니다.
        # 안전하게 일반 딕셔너리로 변환하여 사용합니다.
        key_dict = dict(st.secrets["FIREBASE_KEY"])
        
        # 키 딕셔너리에 private_key가 있는지 확인 (줄바꿈 문자 처리)
        if "private_key" in key_dict:
            key_dict["private_key"] = key_dict["private_key"].replace("\\n", "\n")

        cred = credentials.Certificate(key_dict)
        firebase_admin.initialize_app(cred)
    except Exception as e:
        st.error(f"🔥 데이터베이스 연결 오류: {e}")
        st.stop() # 오류 나면 여기서 멈춤 (더 진행 안 함)

# 앱이 정상적으로 초기화되었을 때만 클라이언트 생성
try:
    db = firestore.client()
except Exception as e:
    st.error("🔥 Firebase 클라이언트를 생성할 수 없습니다. 설정을 확인해주세요.")
    st.stop()

# --- 2. 데이터 암호화 및 유틸리티 함수 ---
def make_code(univ_name, name):
    """연구용 식별 코드 생성"""
    univ_hash = hashlib.sha256(univ_name.encode()).hexdigest()[:2].upper()
    rand_num = random.randint(100, 999)
    return f"{univ_hash}대{rand_num}"

# --- 3. 문제 데이터 로드 ---
@st.cache_data  # 데이터를 매번 다시 읽지 않도록 캐싱
def load_problems():
    try:
        with open('problems.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        # JSON 구조를 리스트의 리스트 형태로 변환 [SET_A, SET_B, SET_C]
        return [data['SET_A'], data['SET_B'], data['SET_C']]
    except FileNotFoundError:
        st.error("❌ 'problems.json' 파일을 찾을 수 없습니다. 파일이 업로드되었는지 확인해주세요.")
        return []
    except json.JSONDecodeError as e:
        st.error(f"❌ 문제 파일(problems.json)에 문법 오류가 있습니다: {e}")
        return []

# 문제 데이터 로드 실행
PROBLEM_SETS = load_problems()

# 데이터 로드 실패 시 중단 방지용 더미 데이터 (앱이 꺼지는 것 방지)
if not PROBLEM_SETS:
    PROBLEM_SETS = [[], [], []]

# 쓰기 문제 (공통 혹은 세트별)

# --- 4. 앱 UI 및 로직 ---
def main():
    st.title("🇰🇷 한국어 실력 진단 평가 (연구용)")
    
    # 세션 상태 초기화
    if 'page' not in st.session_state: st.session_state.page = 'login'
    if 'answers' not in st.session_state: st.session_state.answers = {}
    if 'start_time' not in st.session_state: st.session_state.start_time = None
    
    # 문제 세트 선택 및 셔플 (최초 1회만 실행)
    if 'selected_set_idx' not in st.session_state and PROBLEM_SETS:
        st.session_state.selected_set_idx = random.randint(0, len(PROBLEM_SETS)-1)
        
    if 'shuffled_questions' not in st.session_state and PROBLEM_SETS: 
        raw_questions = PROBLEM_SETS[st.session_state.selected_set_idx]
        st.session_state.shuffled_questions = raw_questions # 순서 그대로 사용 (필요시 random.sample로 셔플 가능)

    # --- 페이지 1: 로그인 ---
    if st.session_state.page == 'login':
        st.info("이 테스트는 연구 목적으로 진행됩니다. 개인정보는 암호화되어 관리됩니다.")
        
        with st.form("login_form"):
            name = st.text_input("이름")
            univ = st.text_input("소속 대학교 (한글로 입력, 예: 한국대학교)")
            email = st.text_input("이메일 (Gmail 권장)")
            submitted = st.form_submit_button("시험 시작하기")
            
            if submitted:
                if not PROBLEM_SETS:
                    st.error("문제 데이터를 불러오지 못해 시험을 시작할 수 없습니다.")
                elif name and univ and email:
                    st.session_state.user_info = {
                        "name": name,
                        "univ": univ,
                        "email": email,
                        "code": make_code(univ, name)
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
        
        # 문제 분리 (객관식 vs 쓰기)
        questions = st.session_state.shuffled_questions
        obj_questions = [q for q in questions if q.get('type') != '쓰기']
        writing_question_list = [q for q in questions if q.get('type') == '쓰기']
        
        # 쓰기 문제가 있으면 가져오고, 없으면 예외 처리
        writing_question = writing_question_list[0] if writing_question_list else None

        with st.form("test_form"):
# 1. 객관식 문제 출력
for idx, q in enumerate(obj_questions):
    # ▼▼▼ [수정된 부분] st.write -> st.markdown으로 변경 ▼▼▼
    st.markdown(f"**{idx+1}. [{q.get('type', '일반')}]** {q['question']}", unsafe_allow_html=True)
    
    # options가 리스트인지 확인
    options = q.get('options', [])
    choice = st.radio(f"{idx+1}번 답안 선택", options, key=f"q_{q['id']}", index=None)
    st.session_state.answers[q['id']] = choice
    st.markdown("---")

# 2. 쓰기 문제 출력
if writing_question:
    # ▼▼▼ [수정된 부분] st.write -> st.markdown으로 변경 ▼▼▼
    st.markdown(f"**[쓰기]** {writing_question['question']}", unsafe_allow_html=True)
    
    # 이미지가 있다면 여기에 st.image 추가 가능
    writing_answer = st.text_area("답안을 작성하세요 (200~300자)", height=200)
else:
    st.warning("쓰기 문제가 로드되지 않았습니다.")
    writing_answer = ""
    # --- 페이지 3: 채점 및 결과 ---
    elif st.session_state.page == 'scoring':
        with st.spinner("AI가 채점 중입니다... 잠시만 기다려주세요."):
            # 1. 객관식 채점
            score_obj = 0
            questions = PROBLEM_SETS[st.session_state.selected_set_idx]
            details = {}
            
            # 쓰기 문제 내용 찾기 (채점 프롬프트용)
            writing_q_text = "그래프 해석"
            
            for q in questions:
                q_type = q.get('type')
                
                if q_type == '쓰기':
                    writing_q_text = q['question']
                    continue # 쓰기는 별도 채점
                
                user_choice = st.session_state.answers.get(q['id'])
                is_correct = False
                
                # 정답 비교 로직
                if user_choice and 'options' in q:
                    try:
                        # 사용자가 선택한 문자열이 보기에 있는지 확인
                        if user_choice in q['options']:
                            choice_idx = q['options'].index(user_choice)
                            if choice_idx == q['answer']:
                                score_obj += q['score']
                                is_correct = True
                    except:
                        pass
                
                details[q['id']] = {
                    "type": q_type,
                    "user_ans": user_choice,
                    "correct": is_correct,
                    "score_earned": q['score'] if is_correct else 0
                }

            # 2. 쓰기 채점 (Gemini API)
            score_writing = 0
            user_writing = st.session_state.answers.get('writing', '')
            
            if user_writing:
                try:
                    model = genai.GenerativeModel('gemini-pro')
                    prompt = f"""
                    당신은 한국어 능력 시험(TOPIK) 채점관입니다.
                    문제: {writing_q_text}
                    학생 답안: {user_writing}
                    
                    평가 기준: 3~4급 수준의 어휘와 문법 사용 능력.
                    점수 범위: 0 ~ 8점 (정수만 출력)
                    출력 형식: 오직 숫자 하나만 출력하세요.
                    """
                    response = model.generate_content(prompt)
                    score_text = response.text.strip()
                    # 숫자만 추출
                    score_writing = int(''.join(filter(str.isdigit, score_text)))
                except Exception as e:
                    print(f"쓰기 채점 오류: {e}")
                    score_writing = 0 
            
            total_score = score_obj + score_writing
            
            # 3. 데이터 저장
            duration = st.session_state.end_time - st.session_state.start_time
            
            doc_data = {
                "name_enc": st.session_state.user_info['name'],
                "univ_enc": st.session_state.user_info['code'],
                "email": st.session_state.user_info['email'],
                "total_score": total_score,
                "score_obj": score_obj,
                "score_writing": score_writing,
                "details": str(details),
                "writing_text": user_writing,
                "duration_sec": int(duration),
                "timestamp": firestore.SERVER_TIMESTAMP
            }
            # 컬렉션 이름 설정
            db.collection("korean_test_results").add(doc_data)
            
            st.success("제출이 완료되었습니다.")
            st.metric("총 점수", f"{total_score}점")
            st.info("결과를 검토하여 연구 프로그램 참여 가능 여부를 메일로 안내드리겠습니다. 기다려 주십시오.")
            
            st.stop()

    # --- 관리자 메뉴 ---
    st.sidebar.markdown("---")
    with st.sidebar.expander("관리자 메뉴"):
        admin_pwd = st.text_input("관리자 암호", type="password")
        if admin_pwd == st.secrets["ADMIN_PASSWORD"]:
            if st.button("데이터 다운로드 (CSV)"):
                docs = db.collection("korean_test_results").stream()
                data = []
                for doc in docs:
                    d = doc.to_dict()
                    # timestamp 객체 처리
                    if 'timestamp' in d and d['timestamp']:
                        d['timestamp'] = d['timestamp'].isoformat()
                    data.append(d)
                
                if data:
                    df = pd.DataFrame(data)
                    csv = df.to_csv(index=False).encode('utf-8-sig')
                    st.download_button("CSV 다운로드", csv, "results.csv", "text/csv")
                else:
                    st.write("아직 저장된 데이터가 없습니다.")

if __name__ == "__main__":
    main()





