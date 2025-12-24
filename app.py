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
import math

# --- [설정] 시험 제한 시간 (초 단위) --- 
TEST_DURATION_SEC = 60 * 60  # 60분

# --- 0. CSS 스타일 적용 (UI 숨기기 + 밑줄 + 타이머 디자인) ---
hide_streamlit_style = """
<style>
    /* 1. 우측 하단 'Manage app' 버튼 숨기기 */
    .stAppDeployButton { display: none; }
    /* 2. 하단 푸터 숨기기 */
    footer { visibility: hidden; }
    /* 3. 햄버거 메뉴 숨기기 */
    #MainMenu { visibility: hidden; }
    
    /* 4. HTML <u> 태그 (밑줄) 스타일 커스텀 */
    u {
        text-decoration: none;
        border-bottom: 2px solid red;
        padding-bottom: 2px;
        font-weight: bold;
    }

    /* 5. 좌측 하단 고정 타이머 디자인 */
    .fixed-timer {
        position: fixed;
        bottom: 20px;
        left: 20px;
        background-color: #FF4B4B;
        color: white;
        padding: 10px 20px;
        border-radius: 30px;
        font-size: 18px;
        font-weight: bold;
        box-shadow: 2px 2px 10px rgba(0,0,0,0.3);
        z-index: 9999;
        font-family: monospace;
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
    st.error("🔥 Firebase 클라이언트를 생성할 수 없습니다.")
    st.stop()

# --- 2. 유틸리티 함수 ---
def make_code(univ_name, name):
    univ_hash = hashlib.sha256(univ_name.encode()).hexdigest()[:2].upper()
    rand_num = random.randint(100, 999)
    return f"{univ_hash}대{rand_num}"

@st.cache_data
def load_all_problems():
    try:
        with open('problems.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        all_problems = []
        for key in ['SET_A', 'SET_B', 'SET_C', 'SET_D', 'SET_E']:
            if key in data:
                all_problems.extend(data[key])
        return all_problems
    except Exception as e:
        st.error(f"문제 로드 오류: {e}")
        return []

ALL_QUESTIONS_POOL = load_all_problems()

# --- 3. 메인 앱 로직 ---
def main():
    st.title("🇰🇷 한국어 실력 진단 평가 (연구용)")
    
    # 세션 상태 초기화
    if 'page' not in st.session_state: st.session_state.page = 'login'
    if 'answers' not in st.session_state: st.session_state.answers = {}
    if 'start_time' not in st.session_state: st.session_state.start_time = None
    if 'end_time' not in st.session_state: st.session_state.end_time = None
    
    # 문제 랜덤 출제 (최초 1회)
    if 'shuffled_questions' not in st.session_state and ALL_QUESTIONS_POOL:
        grammar_pool = [q for q in ALL_QUESTIONS_POOL if q['type'] == '문법']
        vocab_pool = [q for q in ALL_QUESTIONS_POOL if q['type'] == '어휘']
        reading_pool = [q for q in ALL_QUESTIONS_POOL if q['type'] == '읽기']
        writing_pool = [q for q in ALL_QUESTIONS_POOL if q['type'] == '쓰기']
        
        try:
            # 40문항 구성 (비율 조정 가능)
            sel_grammar = random.sample(grammar_pool, 5)
            sel_vocab = random.sample(vocab_pool, 5)
            sel_reading = random.sample(reading_pool, 29)
            sel_writing = random.sample(writing_pool, 1)
            
            st.session_state.shuffled_questions = sel_grammar + sel_vocab + sel_reading + sel_writing
        except ValueError:
            st.error("문제 데이터가 부족하여 세트를 구성할 수 없습니다.")
            st.session_state.shuffled_questions = []

    # --- 페이지 1: 로그인 ---
    if st.session_state.page == 'login':
        st.info("이 테스트는 연구 목적으로 진행됩니다. 개인정보는 암호화되어 관리됩니다.")
        with st.form("login_form"):
            name = st.text_input("이름")
            univ = st.text_input("소속 대학교 (예: 한국대학교)")
            email = st.text_input("이메일 (Gmail 권장)")
            submitted = st.form_submit_button("다음 단계로")
            
            if submitted:
                if name and univ and email:
                    st.session_state.user_info = {
                        "name": name,
                        "univ": univ,
                        "email": email,
                        "code": make_code(univ, name)
                    }
                    st.session_state.page = 'warning' # 경고 페이지로 이동
                    st.rerun()
                else:
                    st.warning("모든 정보를 입력해주세요.")

    # --- 페이지 1.5: 시험 시작 전 경고 (모달 대체) ---
    elif st.session_state.page == 'warning':
        st.warning("⚠️ 주의사항을 확인해주세요")
        st.markdown(f"""
        ### ⏳ 제한 시간 안내
        * 본 시험의 제한 시간은 **{TEST_DURATION_SEC // 60}분**입니다.
        * 좌측 하단에 남은 시간이 표시됩니다.
        * **시간이 종료되면 작성 중인 답안이 자동으로 제출**됩니다.
        * 중간에 브라우저를 닫거나 새로고침하면 답안이 초기화될 수 있습니다.
        
        준비가 되셨으면 아래 버튼을 눌러 시작하세요.
        """)
        
        col1, col2 = st.columns([1, 4])
        if col1.button("✅ 네, 시작합니다", type="primary"):
            st.session_state.start_time = time.time()
            st.session_state.page = 'test'
            st.rerun()

    # --- 페이지 2: 시험 진행 ---
    elif st.session_state.page == 'test':
        # [타이머 로직]
        elapsed_time = time.time() - st.session_state.start_time
        remaining_time = TEST_DURATION_SEC - elapsed_time
        
        # 1. 시간이 다 되었는지 확인 (Python 측 체크)
        if remaining_time <= 0:
            st.session_state.end_time = time.time()
            st.session_state.page = 'scoring'
            st.rerun()
        
        # 2. 자바스크립트 타이머 및 자동 제출 스크립트 삽입
        # (남은 시간을 계산해서 시각적으로 보여주고, 0이 되면 강제로 페이지를 리로드하여 위 파이썬 로직을 트리거함)
        st.components.v1.html(
            f"""
            <div id="timer-display" class="fixed-timer" style="
                position: fixed; bottom: 20px; left: 20px; 
                background-color: #FF4B4B; color: white; 
                padding: 10px 20px; border-radius: 30px; 
                font-size: 18px; font-weight: bold; 
                box-shadow: 2px 2px 10px rgba(0,0,0,0.3); 
                z-index: 9999; font-family: monospace;">
                남은 시간: --:--
            </div>
            <script>
                var timeleft = {remaining_time};
                var downloadTimer = setInterval(function(){
                  if(timeleft <= 0){
                    clearInterval(downloadTimer);
                    document.getElementById("timer-display").innerHTML = "시간 종료! 제출 중...";
                    // 시간이 끝나면 페이지를 새로고침하여 Python의 시간 초과 로직을 실행시킴
                    window.parent.location.reload();
                  } else {
                    var minutes = Math.floor(timeleft / 60);
                    var seconds = Math.floor(timeleft % 60);
                    // 0 채우기
                    if (seconds < 10) seconds = "0" + seconds;
                    if (minutes < 10) minutes = "0" + minutes;
                    
                    document.getElementById("timer-display").innerHTML = "⏳ " + minutes + ":" + seconds;
                  }
                  timeleft -= 1;
                }, 1000);
            </script>
            """, 
            height=0  # 화면 공간 차지 안 함
        )

        st.subheader(f"수험번호: {st.session_state.user_info['code']}")
        st.markdown("---")
        
        questions = st.session_state.shuffled_questions
        obj_questions = [q for q in questions if q.get('type') != '쓰기']
        writing_question_list = [q for q in questions if q.get('type') == '쓰기']
        writing_question = writing_question_list[0] if writing_question_list else None

        # [중요 변경] 데이터 안전을 위해 st.form을 제거하고 즉시 저장 방식으로 변경
        # 이렇게 해야 시간 종료로 강제 제출되어도 클릭해둔 답안이 유지됩니다.
        
        # 1. 객관식 문제 출력
        for idx, q in enumerate(obj_questions):
            st.markdown(f"**{idx+1}. [{q.get('type', '일반')}]** {q['question']}", unsafe_allow_html=True)
            
            if 'passage' in q and q['passage']:
                st.markdown(f"""
                <div style="background-color: #333333; color: #ffffff; padding: 15px; border-radius: 10px; margin-bottom: 10px;">
                    {q['passage'].replace('\n', '<br>')}
                </div>
                """, unsafe_allow_html=True)

            if 'image' in q and q['image']:
                if os.path.exists(q['image']):
                    st.image(q['image'])
            
            options = q.get('options', [])
            # 저장된 답안이 있으면 그것을 기본값으로 설정
            current_ans = st.session_state.answers.get(q['id'], None)
            
            # 라디오 버튼 (클릭 시 자동 저장됨)
            choice = st.radio(
                f"{idx+1}번 답안 선택", 
                options, 
                key=f"q_{q['id']}", 
                index=options.index(current_ans) if current_ans in options else None
            )
            # 답안 업데이트
            st.session_state.answers[q['id']] = choice
            st.markdown("---")
        
        # 2. 쓰기 문제 출력
        if writing_question:
            st.markdown(f"**[쓰기]** {writing_question['question']}", unsafe_allow_html=True)
            
            if 'passage' in writing_question and writing_question['passage']:
                st.markdown(f"""
                <div style="background-color: #333333; color: #ffffff; padding: 15px; border-radius: 10px; margin-bottom: 10px;">
                    {writing_question['passage'].replace('\n', '<br>')}
                </div>
                """, unsafe_allow_html=True)

            if 'image' in writing_question and writing_question['image']:
                if os.path.exists(writing_question['image']):
                    st.image(writing_question['image'])
            
            # 쓰기 답안 (on_change가 없어도 다른 위젯 상호작용 시 저장되지만, 안전을 위해 key 지정)
            writing_ans = st.text_area(
                "답안을 작성하세요 (200~300자)", 
                height=200,
                key="writing_area",
                value=st.session_state.answers.get('writing', '')
            )
            st.session_state.answers['writing'] = writing_ans
        else:
            st.warning("쓰기 문제가 로드되지 않았습니다.")

        st.markdown("---")
        # 수동 제출 버튼
        if st.button("🏁 답안 제출하기", type="primary"):
            st.session_state.end_time = time.time()
            st.session_state.page = 'scoring'
            st.rerun()

    # --- 페이지 3: 채점 및 결과 ---
    elif st.session_state.page == 'scoring':
        st.title("채점 결과")
        with st.spinner("AI가 채점 및 분석 중입니다... (약 10~20초 소요)"):
            
            questions = st.session_state.shuffled_questions
            scores = {"문법": 0, "어휘": 0, "읽기": 0, "쓰기": 0}
            
            score_obj = 0
            max_score = 0
            details = {}
            writing_q_text = "그래프 해석" 

            # [1] 객관식 채점
            for q in questions:
                max_score += q['score']
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

            if user_writing:
                try:
                    model = genai.GenerativeModel('gemini-flash-lastest')
                    prompt = f"""
                    당신은 한국어 능력 시험(TOPIK) 전문 채점관입니다. 
                    아래 학생의 쓰기 답안을 3~4급 수준을 기준으로 평가하고, JSON 포맷으로 출력하세요.

                    [문제] {writing_q_text}
                    [학생 답안] {user_writing}
                    [평가 기준 (총 13점)]
                    1. 내용(5점), 2. 구성(4점), 3. 언어(4점)

                    [출력 포맷 (JSON)]
                    {{
                        "score": <총점 숫자 0~13>,
                        "breakdown": {{ "content": <0~5>, "structure": <0~4>, "grammar": <0~4> }},
                        "feedback": "<피드백 한 문단>",
                        "correction": "<교정본>"
                    }}
                    """
                    response = model.generate_content(prompt)
                    response_text = response.text.strip().replace("```json", "").replace("```", "")
                    writing_analysis = json.loads(response_text)
                    scores["쓰기"] = writing_analysis.get("score", 0)
                except Exception as e:
                    print(f"쓰기 채점 오류: {e}")
                    writing_analysis["feedback"] = "채점 중 오류가 발생했습니다."

            total_score = score_obj + scores["쓰기"]
            
            # [3] 데이터 저장
            if st.session_state.end_time and st.session_state.start_time:
                duration = st.session_state.end_time - st.session_state.start_time
            else:
                duration = TEST_DURATION_SEC # 시간 초과된 경우

            doc_data = {
                "name_enc": st.session_state.user_info['name'],
                "univ_enc": st.session_state.user_info['code'],
                "email": st.session_state.user_info['email'],
                "total_score": total_score,
                "max_score": max_score,
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
            
            # --- 결과 화면 ---
            st.success("🎉 시험이 종료되었습니다!")
            
            col1, col2 = st.columns(2)
            safe_max_score = max_score if max_score > 0 else 100
            progress_value = total_score / safe_max_score
            if progress_value > 1.0: progress_value = 1.0
            
            col1.metric("총점", f"{total_score}점 / {safe_max_score}점")
            col1.progress(progress_value)
            
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
                st.write(f"**[세부 점수]** 내용: {wa['breakdown']['content']}/5, 구성: {wa['breakdown']['structure']}/4, 언어: {wa['breakdown']['grammar']}/4")
                st.info(f"**💡 피드백:**\n{wa['feedback']}")
                with st.expander("원문 및 교정본 비교 보기"):
                    c_a, c_b = st.columns(2)
                    c_a.text_area("내 답안", user_writing, height=150, disabled=True)
                    c_b.text_area("AI 교정본", wa['correction'], height=150, disabled=True)
            else:
                st.warning("제출된 쓰기 답안이 없습니다.")

            st.info("수고하셨습니다. 창을 닫으셔도 됩니다.")
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

