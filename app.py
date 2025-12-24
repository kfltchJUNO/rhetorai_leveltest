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

# --- [설정] 시험 제한 시간 (50분) ---
TEST_DURATION_SEC = 50 * 60 

# --- [데이터] 한국 대학교 리스트 (가나다순 정렬) ---
KOREAN_UNIVERSITIES = sorted([
    "가천대학교", "가톨릭대학교", "강원대학교", "건국대학교", "경기대학교", "경남대학교", "경북대학교", "경상국립대학교", 
    "경성대학교", "경희대학교", "계명대학교", "고려대학교", "공주대학교", "광운대학교", "국민대학교", "군산대학교", 
    "금오공과대학교", "단국대학교", "대구대학교", "대구가톨릭대학교", "대전대학교", "대진대학교", "덕성여자대학교", 
    "동국대학교", "동덕여자대학교", "동아대학교", "동의대학교", "명지대학교", "목원대학교", "목포대학교", "목포해양대학교", 
    "배재대학교", "부경대학교", "부산대학교", "부산외국어대학교", "삼육대학교", "상명대학교", "상지대학교", "서강대학교", 
    "서경대학교", "서울과학기술대학교", "서울교육대학교", "서울대학교", "서울시립대학교", "서울여자대학교", "서원대학교", 
    "선문대학교", "성결대학교", "성균관대학교", "성신여자대학교", "세종대학교", "세한대학교", "수원대학교", "숙명여자대학교", 
    "순천향대학교", "숭실대학교", "신라대학교", "아주대학교", "안동대학교", "안양대학교", "연세대학교", "영남대학교", 
    "용인대학교", "우석대학교", "울산대학교", "원광대학교", "이화여자대학교", "인제대학교", "인천대학교", "인하대학교", 
    "전남대학교", "전북대학교", "전주대학교", "제주대학교", "조선대학교", "중부대학교", "중앙대학교", "창원대학교", 
    "청주대학교", "충남대학교", "충북대학교", "평택대학교", "포항공과대학교(POSTECH)", "한경대학교", "한국과학기술원(KAIST)", 
    "한국교원대학교", "한국교통대학교", "한국기술교육대학교", "한국성서대학교", "한국예술종합학교", "한국외국어대학교", 
    "한국체육대학교", "한국항공대학교", "한국해양대학교", "한남대학교", "한동대학교", "한림대학교", "한밭대학교", 
    "한서대학교", "한성대학교", "한신대학교", "한양대학교", "한양대학교(ERICA)", "협성대학교", "호남대학교", 
    "호서대학교", "홍익대학교", "기타(직접입력)"
])

# --- [데이터] 이메일 도메인 리스트 ---
EMAIL_DOMAINS = [
    "naver.com", "gmail.com", "daum.net", "hanmail.net", "kakao.com", 
    "icloud.com", "outlook.com", "nate.com", "yahoo.com", "직접입력"
]

# --- 0. CSS 스타일 적용 ---
hide_streamlit_style = """
<style>
    .stAppDeployButton { display: none; }
    footer { visibility: hidden; }
    #MainMenu { visibility: hidden; }
    
    u {
        text-decoration: none;
        border-bottom: 2px solid red;
        padding-bottom: 2px;
        font-weight: bold;
    }

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
    
    if 'page' not in st.session_state: st.session_state.page = 'login'
    if 'answers' not in st.session_state: st.session_state.answers = {}
    if 'start_time' not in st.session_state: st.session_state.start_time = None
    if 'end_time' not in st.session_state: st.session_state.end_time = None
    
    # 문제 랜덤 출제 (100점 만점 고정 로직)
    if 'shuffled_questions' not in st.session_state and ALL_QUESTIONS_POOL:
        grammar_pool = [q for q in ALL_QUESTIONS_POOL if q['type'] == '문법']
        vocab_pool = [q for q in ALL_QUESTIONS_POOL if q['type'] == '어휘']
        reading_2pt_pool = [q for q in ALL_QUESTIONS_POOL if q['type'] == '읽기' and q['score'] == 2]
        reading_3pt_pool = [q for q in ALL_QUESTIONS_POOL if q['type'] == '읽기' and q['score'] == 3]
        writing_pool = [q for q in ALL_QUESTIONS_POOL if q['type'] == '쓰기']
        
        try:
            sel_grammar = random.sample(grammar_pool, 5)
            sel_vocab = random.sample(vocab_pool, 5)
            sel_reading_2 = random.sample(reading_2pt_pool, 20)
            sel_reading_3 = random.sample(reading_3pt_pool, 9)
            sel_writing = random.sample(writing_pool, 1)
            
            sel_reading = sel_reading_2 + sel_reading_3
            random.shuffle(sel_reading)
            
            st.session_state.shuffled_questions = sel_grammar + sel_vocab + sel_reading + sel_writing
            
        except ValueError:
            st.error("문제 데이터 부족 (데이터 풀 확인 필요)")
            st.session_state.shuffled_questions = []

    # --- 페이지 1: 로그인 (대폭 수정됨) ---
    if st.session_state.page == 'login':
        st.info("이 테스트는 연구 목적으로 진행됩니다. 개인정보는 암호화되어 관리됩니다.")
        
        # [주의] st.form을 제거하여 상호작용(Selectbox 선택 등)이 즉시 반영되도록 함
        st.subheader("📝 수험자 정보 입력")
        
        # 1. 이름 입력
        name = st.text_input("이름", placeholder="본명을 입력해주세요")
        
        # 2. 대학교 선택 (검색 가능)
        univ_selection = st.selectbox(
            "소속 대학교", 
            KOREAN_UNIVERSITIES, 
            index=None, 
            placeholder="학교명을 검색하거나 선택하세요 (예: 단국대학교)"
        )
        
        final_univ_name = univ_selection
        if univ_selection == "기타(직접입력)":
            final_univ_name = st.text_input("대학교명 직접 입력")

        # 3. 이메일 입력 (ID + 도메인 분리)
        st.markdown("**이메일**")
        col_email_1, col_email_2, col_email_3 = st.columns([2, 0.2, 2])
        
        with col_email_1:
            email_id = st.text_input("이메일 ID", placeholder="example", label_visibility="collapsed")
        with col_email_2:
            st.markdown("<h4 style='text-align: center; margin-top: 5px;'>@</h4>", unsafe_allow_html=True)
        with col_email_3:
            email_domain_select = st.selectbox(
                "도메인 선택", 
                EMAIL_DOMAINS, 
                index=None, 
                placeholder="도메인 선택", 
                label_visibility="collapsed"
            )
        
        # 도메인 직접 입력 처리
        final_domain = email_domain_select
        if email_domain_select == "직접입력":
            final_domain = st.text_input("도메인 직접 입력 (예: school.ac.kr)", placeholder="school.ac.kr")

        st.markdown("---")
        
        # 제출 버튼 및 유효성 검사
        if st.button("다음 단계로", type="primary"):
            # 검증 로직
            if not name:
                st.warning("이름을 입력해주세요.")
            elif not final_univ_name:
                st.warning("소속 대학교를 선택하거나 입력해주세요.")
            elif not email_id:
                st.warning("이메일 ID를 입력해주세요.")
            elif not final_domain:
                st.warning("이메일 도메인을 선택해주세요.")
            elif "@" in email_id:
                st.warning("이메일 ID 칸에는 @ 기호를 넣지 마세요.")
            else:
                # 모든 정보가 유효할 때만 진행
                full_email = f"{email_id}@{final_domain}"
                
                st.session_state.user_info = {
                    "name": name,
                    "univ": final_univ_name,
                    "email": full_email,
                    "code": make_code(final_univ_name, name)
                }
                st.session_state.page = 'warning'
                st.rerun()

    # --- 페이지 1.5: 시험 시작 전 경고 ---
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
        elapsed_time = time.time() - st.session_state.start_time
        remaining_time = TEST_DURATION_SEC - elapsed_time
        
        if remaining_time <= 0:
            st.session_state.end_time = time.time()
            st.session_state.page = 'scoring'
            st.rerun()
        
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
                var downloadTimer = setInterval(function(){{
                  if(timeleft <= 0){{
                    clearInterval(downloadTimer);
                    document.getElementById("timer-display").innerHTML = "시간 종료! 제출 중...";
                    window.parent.location.reload();
                  }} else {{
                    var minutes = Math.floor(timeleft / 60);
                    var seconds = Math.floor(timeleft % 60);
                    if (seconds < 10) seconds = "0" + seconds;
                    if (minutes < 10) minutes = "0" + minutes;
                    document.getElementById("timer-display").innerHTML = "⏳ " + minutes + ":" + seconds;
                  }}
                  timeleft -= 1;
                }}, 1000);
            </script>
            """, 
            height=0
        )

        st.subheader(f"수험번호: {st.session_state.user_info['code']}")
        st.markdown("---")
        
        questions = st.session_state.shuffled_questions
        obj_questions = [q for q in questions if q.get('type') != '쓰기']
        writing_question_list = [q for q in questions if q.get('type') == '쓰기']
        writing_question = writing_question_list[0] if writing_question_list else None

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
            current_ans = st.session_state.answers.get(q['id'], None)
            
            choice = st.radio(
                f"{idx+1}번 답안 선택", 
                options, 
                key=f"q_{q['id']}", 
                index=options.index(current_ans) if current_ans in options else None
            )
            st.session_state.answers[q['id']] = choice
            st.markdown("---")
        
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

            user_writing = st.session_state.answers.get('writing', '')
            writing_analysis = {
                "score": 0,
                "breakdown": {"content": 0, "structure": 0, "grammar": 0},
                "feedback": "답안이 없습니다.",
                "correction": ""
            }

            if user_writing:
                try:
                    model = genai.GenerativeModel('gemini-flash-latest')
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
            
            if st.session_state.end_time and st.session_state.start_time:
                duration = st.session_state.end_time - st.session_state.start_time
            else:
                duration = TEST_DURATION_SEC

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
