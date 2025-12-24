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

# --- 0. CSS 스타일 적용 (UI 숨기기 + 밑줄 스타일) ---
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

    /* 3. 우측 상단 햄버거 메뉴 숨기기 (선택사항) */
    #MainMenu {
        visibility: hidden;
    }

    /* 4. HTML <u> 태그 (밑줄) 스타일 커스텀 */
    u {
        text-decoration: none;
        border-bottom: 2px solid red;  /* 빨간색 밑줄 */
        padding-bottom: 2px;
        font-weight: bold;
    }
</style>
"""

# --- 1. 설정 및 초기화 ---
st.set_page_config(page_title="한국어 간이 레벨 테스트", layout="wide")
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# (1) Gemini 설정
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
except Exception as e:
    st.error(f"Gemini API 설정 오류: {e}")

# (2) Firebase 설정
if not firebase_admin._apps:
    try:
        key_dict = dict(st.secrets["FIREBASE_KEY"])
        if "private_key" in key_dict:
            key_dict["private_key"] = key_dict["private_key"].replace("\\n", "\n")

        cred = credentials.Certificate(key_dict)
        firebase_admin.initialize_app(cred)
    except Exception as e:
        st.error(f"🔥 데이터베이스 연결 오류: {e}")
        st.stop()

try:
    db = firestore.client()
except Exception as e:
    st.error("🔥 Firebase 클라이언트를 생성할 수 없습니다. 설정을 확인해주세요.")
    st.stop()

# --- 2. 유틸리티 함수 ---
def make_code(univ_name, name):
    """연구용 식별 코드 생성"""
    univ_hash = hashlib.sha256(univ_name.encode()).hexdigest()[:2].upper()
    rand_num = random.randint(100, 999)
    return f"{univ_hash}대{rand_num}"

# --- 3. 문제 데이터 로드 ---
@st.cache_data
def load_problems():
    try:
        with open('problems.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        return [data['SET_A'], data['SET_B'], data['SET_C'],data['SET_D'],data['SET_E']]
    except FileNotFoundError:
        st.error("❌ 'problems.json' 파일을 찾을 수 없습니다.")
        return []
    except json.JSONDecodeError as e:
        st.error(f"❌ 문제 파일 문법 오류: {e}")
        return []

PROBLEM_SETS = load_problems()
if not PROBLEM_SETS:
    PROBLEM_SETS = [[], [], []]

# --- 4. 메인 앱 로직 ---
def main():
    st.title("🇰🇷 한국어 실력 진단 평가 (연구용)")
    
    # 세션 상태 초기화
    if 'page' not in st.session_state: st.session_state.page = 'login'
    if 'answers' not in st.session_state: st.session_state.answers = {}
    if 'start_time' not in st.session_state: st.session_state.start_time = None
    if 'end_time' not in st.session_state: st.session_state.end_time = None
    
    # 문제 세트 선택 및 셔플 (최초 1회만)
    if 'selected_set_idx' not in st.session_state and PROBLEM_SETS:
        st.session_state.selected_set_idx = random.randint(0, len(PROBLEM_SETS)-1)
        
    if 'shuffled_questions' not in st.session_state and PROBLEM_SETS: 
        raw_questions = PROBLEM_SETS[st.session_state.selected_set_idx]
        st.session_state.shuffled_questions = raw_questions

    # --- 페이지 1: 로그인 ---
    if st.session_state.page == 'login':
        st.info("이 테스트는 연구 목적으로 진행됩니다. 개인정보는 암호화되어 관리됩니다.")
        
        with st.form("login_form"):
            name = st.text_input("이름")
            univ = st.text_input("소속 대학교 (예: 한국대학교)")
            email = st.text_input("이메일 (Gmail 권장)")
            submitted = st.form_submit_button("시험 시작하기")
            
            if submitted:
                if not PROBLEM_SETS:
                    st.error("문제 데이터를 불러오지 못했습니다.")
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
        
        questions = st.session_state.shuffled_questions
        obj_questions = [q for q in questions if q.get('type') != '쓰기']
        writing_question_list = [q for q in questions if q.get('type') == '쓰기']
        writing_question = writing_question_list[0] if writing_question_list else None

        # [수정됨] 들여쓰기가 맞춰진 form 내부 코드
        with st.form("test_form"):
            # 1. 객관식 문제 출력
            for idx, q in enumerate(obj_questions):
                # 문제 텍스트 출력 (밑줄 포함)
                st.markdown(f"**{idx+1}. [{q.get('type', '일반')}]** {q['question']}", unsafe_allow_html=True)
                
                # [추가됨] 지문(passage)이 있으면 출력 (박스로 감싸서 보기 좋게)
                if 'passage' in q and q['passage']:
                    st.info(q['passage']) # 또는 st.text_area(..., disabled=True)

                # [추가됨] 이미지가 있으면 출력
                if 'image' in q and q['image']:
                    # 이미지 경로가 실제 파일로 존재하는지 확인 (선택 사항이지만 안전함)
                    if os.path.exists(q['image']):
                        st.image(q['image'], caption=f"문제 {idx+1}번 자료")
                    else:
                        st.warning(f"이미지를 찾을 수 없습니다: {q['image']}")
                
                # 보기 출력
                options = q.get('options', [])
                choice = st.radio(f"{idx+1}번 답안 선택", options, key=f"q_{q['id']}", index=None)
                st.session_state.answers[q['id']] = choice
                st.markdown("---")
            
            # 2. 쓰기 문제 출력
            if writing_question:
                st.markdown(f"**[쓰기]** {writing_question['question']}", unsafe_allow_html=True)
                
                # [추가됨] 쓰기 문제 지문/자료 출력
                if 'passage' in writing_question and writing_question['passage']:
                     st.info(writing_question['passage'])

                # [추가됨] 쓰기 문제 이미지 출력
                if 'image' in writing_question and writing_question['image']:
                    if os.path.exists(writing_question['image']):
                        st.image(writing_question['image'], caption="쓰기 문제 자료")
                
                writing_answer = st.text_area("답안을 작성하세요 (200~300자)", height=200)
                st.session_state.answers['writing'] = writing_answer
            else:
                st.warning("쓰기 문제가 로드되지 않았습니다.")
                st.session_state.answers['writing'] = ""
            
            # ... (이하 제출 버튼 코드는 동일)
            
            # 제출 버튼
            submitted = st.form_submit_button("제출 및 채점하기")
            
            if submitted:
                st.session_state.end_time = time.time()
                st.session_state.page = 'scoring'
                st.rerun()

    # --- 페이지 3: 채점 및 결과 ---
    elif st.session_state.page == 'scoring':
        st.title("채점 결과")
        with st.spinner("AI가 채점 및 분석 중입니다... (약 10~20초 소요)"):
            
            # [1] 객관식 채점 및 유형별 점수 계산
            questions = PROBLEM_SETS[st.session_state.selected_set_idx]
            
            # 점수 집계용 변수 초기화
            scores = {
                "문법": 0,
                "어휘": 0,
                "읽기": 0,
                "쓰기": 0
            }
            
            score_obj = 0  # 객관식 총점
            details = {}   # 문제별 상세 결과
            
            writing_q_text = "그래프 해석" # 기본값

            for q in questions:
                q_type = q.get('type')
                
                # 쓰기 문제는 건너뛰고 텍스트만 저장
                if q_type == '쓰기':
                    writing_q_text = q['question']
                    continue
                
                user_choice = st.session_state.answers.get(q['id'])
                is_correct = False
                
                # 정답 확인 로직
                if user_choice and 'options' in q:
                    try:
                        if user_choice in q['options']:
                            choice_idx = q['options'].index(user_choice)
                            if choice_idx == q['answer']:
                                # 정답인 경우
                                point = q['score']
                                score_obj += point
                                is_correct = True
                                
                                # 유형별 점수 합산 (DB 키와 매핑)
                                if q_type in scores:
                                    scores[q_type] += point
                    except:
                        pass
                
                details[q['id']] = {
                    "type": q_type,
                    "user_ans": user_choice,
                    "correct": is_correct,
                    "score_earned": q['score'] if is_correct else 0
                }

            # [2] 쓰기 채점 (Gemini) - 상세 분석 요청
            user_writing = st.session_state.answers.get('writing', '')
            writing_analysis = {
                "score": 0,
                "breakdown": {"content": 0, "structure": 0, "grammar": 0},
                "feedback": "답안이 없습니다.",
                "correction": ""
            }

            if user_writing:
                try:
                    model = genai.GenerativeModel('gemini-pro')
                    # 프롬프트를 상세하게 변경하여 JSON 출력을 유도
                    prompt = f"""
                    당신은 한국어 능력 시험(TOPIK) 전문 채점관입니다. 
                    아래 학생의 쓰기 답안을 3~4급 수준을 기준으로 평가하고, 반드시 아래의 JSON 포맷으로만 출력하세요. (마크다운이나 설명 없이 JSON만 출력)

                    [문제]
                    {writing_q_text}

                    [학생 답안]
                    {user_writing}

                    [평가 기준 (총 8점)]
                    1. 내용(3점): 문제에서 요구한 내용을 모두 포함했는가?
                    2. 구성(3점): 글의 흐름이 논리적인가?
                    3. 언어(2점): 어휘와 문법이 정확하고 고급스러운가?

                    [출력 포맷 (JSON)]
                    {{
                        "score": <총점 숫자 0~8>,
                        "breakdown": {{
                            "content": <내용 점수 0~3>,
                            "structure": <구성 점수 0~3>,
                            "grammar": <언어 점수 0~2>
                        }},
                        "feedback": "<학생을 위한 구체적인 피드백 한 문단>",
                        "correction": "<어색한 문장을 자연스럽게 고친 교정본 전체>"
                    }}
                    """
                    response = model.generate_content(prompt)
                    
                    # 응답 텍스트 정리 (JSON 파싱을 위해)
                    response_text = response.text.strip()
                    if response_text.startswith("```json"):
                        response_text = response_text.replace("```json", "").replace("```", "")
                    
                    # JSON 변환
                    writing_analysis = json.loads(response_text)
                    scores["쓰기"] = writing_analysis.get("score", 0)
                    
                except Exception as e:
                    print(f"쓰기 채점 오류: {e}")
                    # 오류 시 기본값 유지 (0점)
                    writing_analysis["feedback"] = f"채점 중 오류가 발생했습니다: {e}"

            total_score = score_obj + scores["쓰기"]
            
            # [3] 데이터 저장 (세분화된 정보 포함)
            duration = st.session_state.end_time - st.session_state.start_time
            
            doc_data = {
                "name_enc": st.session_state.user_info['name'],
                "univ_enc": st.session_state.user_info['code'],
                "email": st.session_state.user_info['email'],
                
                # 점수 정보 (세분화)
                "total_score": total_score,
                "score_grammar": scores["문법"],
                "score_vocab": scores["어휘"],
                "score_reading": scores["읽기"],
                "score_writing": scores["쓰기"], # 총 쓰기 점수
                
                # 상세 데이터
                "details_obj": str(details), # 객관식 상세 (문자열로 저장)
                "writing_original": user_writing, # 학생 원본 답안
                
                # 쓰기 상세 분석 (Map 형태로 저장하여 관리자 페이지에서 보기 좋게)
                "writing_analysis": writing_analysis, 
                
                "duration_sec": int(duration),
                "timestamp": firestore.SERVER_TIMESTAMP
            }
            
            db.collection("korean_test_results").add(doc_data)
            
            # --- 결과 화면 출력 ---
            st.success("🎉 채점이 완료되었습니다!")
            
            # 1. 종합 점수
            col1, col2 = st.columns(2)
            col1.metric("총점", f"{total_score}점 / 80점")
            col1.progress(total_score / 80)
            
            # 2. 영역별 점수
            st.subheader("📊 영역별 점수")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("문법", f"{scores['문법']}점")
            c2.metric("어휘", f"{scores['어휘']}점")
            c3.metric("읽기", f"{scores['읽기']}점")
            c4.metric("쓰기", f"{scores['쓰기']}점")
            
            # 3. 쓰기 상세 피드백 표시
            st.markdown("---")
            st.subheader("📝 쓰기 AI 분석 결과")
            if user_writing:
                wa = writing_analysis
                st.write(f"**[세부 점수]** 내용: {wa['breakdown']['content']}/3, 구성: {wa['breakdown']['structure']}/3, 언어: {wa['breakdown']['grammar']}/2")
                
                st.info(f"**💡 피드백:**\n{wa['feedback']}")
                
                with st.expander("원문 및 교정본 비교 보기"):
                    col_a, col_b = st.columns(2)
                    col_a.text_area("내 답안", user_writing, height=150, disabled=True)
                    col_b.text_area("AI 교정본", wa['correction'], height=150, disabled=True)
            else:
                st.warning("제출된 쓰기 답안이 없습니다.")

            st.info("결과가 저장되었습니다. 연구 프로그램 참여 가능 여부는 추후 메일로 안내드립니다.")
            st.stop()

    # --- 관리자 메뉴 (사이드바) ---
    st.sidebar.markdown("---")
    with st.sidebar.expander("관리자 메뉴"):
        admin_pwd = st.text_input("관리자 암호", type="password")
        if admin_pwd == st.secrets["ADMIN_PASSWORD"]:
            if st.button("데이터 다운로드 (CSV)"):
                docs = db.collection("korean_test_results").stream()
                data = []
                for doc in docs:
                    d = doc.to_dict()
                    if 'timestamp' in d and d['timestamp']:
                        d['timestamp'] = d['timestamp'].isoformat()
                    data.append(d)
                
                if data:
                    df = pd.DataFrame(data)
                    csv = df.to_csv(index=False).encode('utf-8-sig')
                    st.download_button("CSV 다운로드", csv, "results.csv", "text/csv")
                else:
                    st.write("데이터가 없습니다.")

if __name__ == "__main__":
    main()



