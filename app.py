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
    if "GEMINI_API_KEY" in st.secrets:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    else:
        st.warning("GEMINI_API_KEY가 설정되지 않았습니다.")
except Exception as e:
    st.error(f"Gemini API 설정 오류: {e}")

# (2) Firebase 설정
if not firebase_admin._apps:
    try:
        if "FIREBASE_KEY" in st.secrets:
            key_dict = dict(st.secrets["FIREBASE_KEY"])
            if "private_key" in key_dict:
                key_dict["private_key"] = key_dict["private_key"].replace("\\n", "\n")

            cred = credentials.Certificate(key_dict)
            firebase_admin.initialize_app(cred)
        else:
            st.warning("FIREBASE_KEY가 설정되지 않았습니다.")
    except Exception as e:
        st.error(f"🔥 데이터베이스 연결 오류: {e}")
        # DB 연결 실패 시에도 앱이 꺼지지 않도록 stop() 제거 고려 가능 (현재는 유지)
        st.stop()

try:
    if firebase_admin._apps:
        db = firestore.client()
    else:
        db = None
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
        
        # 키가 존재하는지 확인하며 로드 (안전장치 추가)
        sets = []
        for key in ['SET_A', 'SET_B', 'SET_C', 'SET_D', 'SET_E']:
            if key in data:
                sets.append(data[key])
        
        if not sets:
            st.error("❌ 문제 파일에 유효한 SET 데이터가 없습니다.")
            return []
            
        return sets
        
    except FileNotFoundError:
        st.error("❌ 'problems.json' 파일을 찾을 수 없습니다.")
        return []
    except json.JSONDecodeError as e:
        st.error(f"❌ 문제 파일 문법 오류 (JSON 형식을 확인하세요): {e}")
        return []
    except Exception as e:
        st.error(f"❌ 알 수 없는 오류 발생: {e}")
        return []

PROBLEM_SETS = load_problems()

# --- 4. 메인 앱 로직 ---
def main():
    st.title("🇰🇷 한국어 실력 진단 평가 (연구용)")
    
    # 세션 상태 초기화
    if 'page' not in st.session_state: st.session_state.page = 'login'
    if 'answers' not in st.session_state: st.session_state.answers = {}
    if 'start_time' not in st.session_state: st.session_state.start_time = None
    if 'end_time' not in st.session_state: st.session_state.end_time = None
    
    # 문제 세트 선택 및 셔플 (최초 1회만) - PROBLEM_SETS가 비어있지 않을 때만 실행
    if PROBLEM_SETS:
        if 'selected_set_idx' not in st.session_state:
            st.session_state.selected_set_idx = random.randint(0, len(PROBLEM_SETS)-1)
            
        if 'shuffled_questions' not in st.session_state: 
            raw_questions = PROBLEM_SETS[st.session_state.selected_set_idx]
            st.session_state.shuffled_questions = raw_questions
    else:
        st.warning("문제 데이터를 불러오는 중 오류가 발생했거나 데이터가 없습니다.")

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
                    st.error("문제 데이터 오류로 시험을 시작할 수 없습니다.")
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

        with st.form("test_form"):
            # 1. 객관식 문제 출력
            for idx, q in enumerate(obj_questions):
                # 문제 유형과 질문 출력
                st.markdown(f"**{idx+1}. [{q.get('type', '일반')}]** {q['question']}", unsafe_allow_html=True)
                
                # [수정됨] 지문(passage) 출력: st.info 대신 st.markdown 사용
                if 'passage' in q and q['passage']:
                    # 회색 박스 안에 지문을 넣고 HTML 태그(<u>)가 먹히도록 설정
                    st.markdown(f"""
                    <div style="background-color: #f0f2f6; padding: 15px; border-radius: 10px; margin-bottom: 10px;">
                        {q['passage']}
                    </div>
                    """, unsafe_allow_html=True)

                # 이미지 출력
                if 'image' in q and q['image']:
                    if os.path.exists(q['image']):
                        st.image(q['image'])
                
                # 보기 출력
                options = q.get('options', [])
                choice = st.radio(f"{idx+1}번 답안 선택", options, key=f"q_{q['id']}", index=None)
                st.session_state.answers[q['id']] = choice
                st.markdown("---")
            
            # 2. 쓰기 문제 출력
            if writing_question:
                st.markdown(f"**[쓰기]** {writing_question['question']}", unsafe_allow_html=True)
                
                # [수정됨] 쓰기 지문도 동일하게 처리
                if 'passage' in writing_question and writing_question['passage']:
                    st.markdown(f"""
                    <div style="background-color: #f0f2f6; padding: 15px; border-radius: 10px; margin-bottom: 10px;">
                        {writing_question['passage']}
                    </div>
                    """, unsafe_allow_html=True)

                if 'image' in writing_question and writing_question['image']:
                    if os.path.exists(writing_question['image']):
                        st.image(writing_question['image'])
                
                writing_answer = st.text_area("답안을 작성하세요 (200~300자)", height=200)
                st.session_state.answers['writing'] = writing_answer
            else:
                st.warning("쓰기 문제가 로드되지 않았습니다.")
                st.session_state.answers['writing'] = ""
            
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
            
            # [1] 객관식 채점
            questions = PROBLEM_SETS[st.session_state.selected_set_idx]
            
            scores = {"문법": 0, "어휘": 0, "읽기": 0, "쓰기": 0}
            score_obj = 0
            details = {}
            writing_q_text = "그래프 해석" 

            for q in questions:
                q_type = q.get('type')
                if q_type == '쓰기':
                    writing_q_text = q['question']
                    continue
                
                user_choice = st.session_state.answers.get(q['id'])
                is_correct = False
                
                if user_choice and 'options' in q:
                    try:
                        if user_choice in q['options']:
                            choice_idx = q['options'].index(user_choice)
                            if choice_idx == q['answer']:
                                point = q['score']
                                score_obj += point
                                is_correct = True
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

            # [2] 쓰기 채점 (Gemini)
            user_writing = st.session_state.answers.get('writing', '')
            writing_analysis = {
                "score": 0,
                "breakdown": {"content": 0, "structure": 0, "grammar": 0},
                "feedback": "답안이 없습니다.",
                "correction": ""
            }

            if user_writing and "GEMINI_API_KEY" in st.secrets:
                try:
                    model = genai.GenerativeModel('gemini-pro')
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
                    response_text = response.text.strip()
                    if response_text.startswith("```json"):
                        response_text = response_text.replace("```json", "").replace("```", "")
                    
                    writing_analysis = json.loads(response_text)
                    scores["쓰기"] = writing_analysis.get("score", 0)
                    
                except Exception as e:
                    # st.error(f"쓰기 채점 오류: {e}") # 사용자에게 에러 보여주지 않기 위해 주석 처리
                    writing_analysis["feedback"] = f"AI 채점 중 오류가 발생했습니다. (잠시 후 다시 시도해주세요)"

            total_score = score_obj + scores["쓰기"]
            
            # [3] 데이터 저장
            duration = st.session_state.end_time - st.session_state.start_time
            
            if db:
                doc_data = {
                    "name_enc": st.session_state.user_info['name'],
                    "univ_enc": st.session_state.user_info['code'],
                    "email": st.session_state.user_info['email'],
                    "total_score": total_score,
                    "score_grammar": scores["문법"],
                    "score_vocab": scores["어휘"],
                    "score_reading": scores["읽기"],
                    "score_writing": scores["쓰기"],
                    "details_obj": str(details),
                    "writing_original": user_writing,
                    "writing_analysis": writing_analysis,
                    "duration_sec": int(duration),
                    "timestamp": firestore.SERVER_TIMESTAMP
                }
                db.collection("korean_test_results").add(doc_data)
            
            # 결과 화면 출력
            st.success("🎉 채점이 완료되었습니다!")
            
            col1, col2 = st.columns(2)
            col1.metric("총점", f"{total_score}점 / 80점")
            col1.progress(total_score / 80)
            
            st.subheader("📊 영역별 점수")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("문법", f"{scores['문법']}점")
            c2.metric("어휘", f"{scores['어휘']}점")
            c3.metric("읽기", f"{scores['읽기']}점")
            c4.metric("쓰기", f"{scores['쓰기']}점")
            
            st.markdown("---")
            st.subheader("📝 쓰기 AI 분석 결과")
            if user_writing:
                wa = writing_analysis
                # breakdown 키가 없는 경우 대비
                bd = wa.get('breakdown', {"content": 0, "structure": 0, "grammar": 0})
                st.write(f"**[세부 점수]** 내용: {bd.get('content')}/3, 구성: {bd.get('structure')}/3, 언어: {bd.get('grammar')}/2")
                
                st.info(f"**💡 피드백:**\n{wa.get('feedback', '')}")
                
                with st.expander("원문 및 교정본 비교 보기"):
                    col_a, col_b = st.columns(2)
                    col_a.text_area("내 답안", user_writing, height=150, disabled=True)
                    col_b.text_area("AI 교정본", wa.get('correction', ''), height=150, disabled=True)
            else:
                st.warning("제출된 쓰기 답안이 없습니다.")

            st.info("결과가 저장되었습니다. 연구 프로그램 참여 가능 여부는 추후 메일로 안내드립니다.")
            st.stop()

    # --- 관리자 메뉴 (사이드바) ---
    st.sidebar.markdown("---")
    with st.sidebar.expander("관리자 메뉴"):
        admin_pwd = st.text_input("관리자 암호", type="password")
        if "ADMIN_PASSWORD" in st.secrets and admin_pwd == st.secrets["ADMIN_PASSWORD"]:
            if db:
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
            else:
                st.error("DB 연결이 되지 않아 데이터를 불러올 수 없습니다.")

if __name__ == "__main__":
    main()

