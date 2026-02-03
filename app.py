import base64
import os
from statistics import correlation
import psycopg2
from psycopg2.extras import DictCursor
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from dotenv import load_dotenv
from datetime import datetime
import pandas as pd
import seaborn as sns
import matplotlib
matplotlib.use('Agg') # 이 줄이 에러를 막아주는 핵심입니다.
import matplotlib.pyplot as plt
import io
import json

# 로컬 환경에서는 .env를 읽고, Azure에서는 패스.
if os.path.exists('.env'):
    load_dotenv()
app = Flask(__name__)
app.secret_key = os.urandom(24)

# 데이터베이스 연결 함수
def get_db_connection():
    conn = psycopg2.connect(
        host=os.getenv('DB_HOST'),
        port=os.getenv('DB_PORT'),
        dbname=os.getenv('DB_NAME'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        sslmode='require' #Azure를 위해 반드시 추가
       ,options="-c timezone=Asia/Seoul"
    )
    print('get_db_connection', conn)
    conn.autocommit = True
    return conn

@app.route('/')
def index():
    # 1. 데이터 베이스에 접속
    conn = get_db_connection()
    print('get_db_connection', conn)
    cursor = conn.cursor(cursor_factory=DictCursor)
    # 2. SELECT
    cursor.execute("SELECT id, title, author, created_at, view_count, like_count FROM board.posts ORDER BY created_at DESC")
    posts = cursor.fetchall()
    cursor.close()
    conn.close()
    # 3. index.html 파일에 변수로 넘겨주기
    return render_template('index.html', posts = posts)

@app.route('/create/', methods=['GET'] )
def create_form():
    return render_template('create.html')

@app.route('/create/',methods=['POST']  )
def create_post():
    #1. 폼에 있는 정보들을 get
    title = request.form.get('title')
    author = request.form.get('author')
    content = request.form.get('content')

    if not title or not author or not content:
        flash('모든 필드를 똑바로 채워주세요!!!!')
        return redirect(url_for('create_form'))
    
    # 1. 데이터 베이스에 접속
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=DictCursor)
    # 2. INSERT
    cursor.execute("INSERT INTO board.posts (title, content, author) VALUES (%s, %s, %s) RETURNING id", (title,author,content ))
    post_id = cursor.fetchone()[0]
    cursor.close()
    conn.close()
    flash('게시글이 성공적으로 등록되었음')
    return redirect(url_for('view_post', post_id=post_id))

@app.route('/post/<int:post_id>')
def view_post(post_id):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=DictCursor)
    
    cursor.execute('UPDATE board.posts SET view_count = view_count + 1 WHERE id = %s', (post_id,))
    
    cursor.execute('SELECT * FROM board.posts WHERE id = %s', (post_id,))
    post = cursor.fetchone()
    
    if post is None:
        cursor.close()
        conn.close()
        flash('게시글을 찾을 수 없습니다.')
        return redirect(url_for('index'))
    
    cursor.execute('SELECT * FROM board.comments WHERE post_id = %s ORDER BY created_at', (post_id,))
    comments = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    user_ip = request.remote_addr
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM board.likes WHERE post_id = %s AND user_ip = %s', (post_id, user_ip))
    liked = cursor.fetchone()[0] > 0
    cursor.close()
    conn.close()
    
    return render_template('view.html', post=post, comments=comments, liked=liked)

@app.route('/edit/<int:post_id>', methods=['GET'])
def edit_form(post_id):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=DictCursor)
    cursor.execute('SELECT * FROM board.posts WHERE id = %s', (post_id,))
    post = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if post is None:
        flash('게시글을 찾을 수 없습니다.')
        return redirect(url_for('index'))
    
    return render_template('edit.html', post=post)

@app.route('/edit/<int:post_id>', methods=['POST'])
def edit_post(post_id):
    title = request.form.get('title')
    content = request.form.get('content')
    
    if not title or not content:
        flash('제목과 내용을 모두 입력해주세요.')
        return redirect(url_for('edit_form', post_id=post_id))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        'UPDATE board.posts SET title = %s, content = %s, updated_at = %s WHERE id = %s',
        (title, content, datetime.now(), post_id)
    )
    cursor.close()
    conn.close()
    
    flash('게시글이 성공적으로 수정되었습니다.')
    return redirect(url_for('view_post', post_id=post_id))

@app.route('/delete/<int:post_id>', methods=['POST'])
def delete_post(post_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM board.posts WHERE id = %s', (post_id,))
    cursor.close()
    conn.close()
    
    flash('게시글이 성공적으로 삭제되었습니다.')
    return redirect(url_for('index'))

@app.route('/post/comment/<int:post_id>', methods=['POST'])
def add_comment(post_id):
    author = request.form.get('author')
    content = request.form.get('content')
    
    if not author or not content:
        flash('작성자와 내용을 모두 입력해주세요.')
        return redirect(url_for('view_post', post_id=post_id))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO board.comments (post_id, author, content) VALUES (%s, %s, %s)',
        (post_id, author, content)
    )
    cursor.close()
    conn.close()
    
    flash('댓글이 등록되었습니다.')
    return redirect(url_for('view_post', post_id=post_id))

@app.route('/post/like/<int:post_id>', methods=['POST'])
def like_post(post_id):
    user_ip = request.remote_addr
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM board.likes WHERE post_id = %s AND user_ip = %s', (post_id, user_ip))
    already_liked = cursor.fetchone()[0] > 0
    
    if already_liked:
        cursor.execute('DELETE FROM board.likes WHERE post_id = %s AND user_ip = %s', (post_id, user_ip))
        cursor.execute('UPDATE board.posts SET like_count = like_count - 1 WHERE id = %s', (post_id,))
        message = '좋아요가 취소되었습니다.'
    else:
        cursor.execute('INSERT INTO board.likes (post_id, user_ip) VALUES (%s, %s)', (post_id, user_ip))
        cursor.execute('UPDATE board.posts SET like_count = like_count + 1 WHERE id = %s', (post_id,))
        message = '좋아요가 등록되었습니다.'
    
    cursor.close()
    conn.close()   
    flash(message)
    return redirect(url_for('view_post', post_id=post_id))

@app.route('/fms')
def fms_result():
    # 1. 데이터 베이스에 접속
    conn = get_db_connection()
    print('get_db_connection', conn)
    cursor = conn.cursor(cursor_factory=DictCursor)

    page = request.args.get('page', 1, type=int)
    per_page = 10
    offset = (page - 1) * per_page

    # 1. 전체 데이터 개수 조회
    count_query = "SELECT COUNT(*) as cnt FROM fms.chick_info"
    cursor.execute(count_query)  # 여기서 먼저 실행하고
    count_result = cursor.fetchone() # 여기서 따로 가져옵니다.
    
    # DB 설정에 따라 결과가 dict일 수도, tuple일 수도 있습니다.
    if isinstance(count_result, dict):
        total_count = count_result['cnt']
    else:
        total_count = count_result[0]

    total_pages = (total_count + per_page - 1) // per_page

    # 2. 현재 페이지 데이터 조회
    query = f"SELECT * FROM fms.chick_info ci LIMIT %s OFFSET %s"
    cursor.execute(query, (per_page, offset)) # 보안을 위해 f-string보다 파라미터 바인딩 추천
    results = cursor.fetchall()

    return render_template('fms_result.html', 
                           results=results, 
                           page=page, 
                           total_pages=total_pages)

def get_db_data():
     # 1. 데이터 베이스에 접속
    conn = get_db_connection()
    print('get_db_connection', conn)
    cursor = conn.cursor(cursor_factory=DictCursor)

    # 1. 전체 데이터 개수 조회
    count_query = "SELECT * FROM board.companies"
    cursor.execute(count_query)  # 여기서 먼저 실행하고

    query = 'SELECT * FROM board.companies LIMIT 10'
    df = pd.read_sql(query, conn)
    return df

# 한글 폰트 설정 함수
def set_korean_font():
    plt.rc('font', family='Malgun Gothic')
    # 마이너스 기호 깨짐 방지
    plt.rcParams['axes.unicode_minus'] = False

def create_plot(df):
    sns.set_theme(style="whitegrid")

    # 폰트 설정 적용
    set_korean_font()
    
    """Seaborn 차트 4개를 생성하고 base64 리스트로 반환"""
    
    encoded_images = []

    # 1. Top 10 Employees Count (막대 차트)
    plt.figure(figsize=(8, 5))
    ax1 = sns.barplot(x='employees_count', y='name', data=df, palette='viridis')
    ax1.set_title('Top 10 기업 고용 인원 현황', fontsize=15)
    encoded_images.append(plt_to_base64())

    # 2. 국가별 기업 비중 (원형 차트 - Matplotlib 활용)
    plt.figure(figsize=(8, 5))
    country_counts = df['country'].value_counts()
    plt.pie(country_counts, labels=country_counts.index, autopct='%1.1f%%', 
            colors=sns.color_palette('pastel'), startangle=140)
    plt.title('상위 기업 국가별 분포', fontsize=15)
    encoded_images.append(plt_to_base64())

    # 3. 고용 및 주가 사분면 분석
    plt.figure(figsize=(10, 7))

    # 1. 산점도 그리기
    sns.scatterplot(data=df, x='price (USD)', y='employees_count', 
                    hue='country', s=200, palette='Set1', edgecolor='black', alpha=0.7)

    # 2. 평균선 그리기 (사분면의 기준)
    plt.axhline(df['employees_count'].mean(), color='gray', linestyle='--', linewidth=1) # 가로 평균선
    plt.axvline(df['price (USD)'].mean(), color='gray', linestyle='--', linewidth=1)   # 세로 평균선

    # 3. 사분면 구역 설명 텍스트 추가
    # 오른쪽 상단 (주가 높고 고용 많음)
    plt.text(df['price (USD)'].max()*0.85, df['employees_count'].max()*0.95, 
             '고가치·대규모', fontsize=12, color='red', fontweight='bold', alpha=0.5)
    # 왼쪽 하단 (주가 낮고 고용 적음)
    plt.text(df['price (USD)'].min(), df['employees_count'].min(), 
             '신생·중소규모', fontsize=12, color='blue', fontweight='bold', alpha=0.5)

    # 4. 기업별 이름 표시 (매우 중요 - 직관성의 핵심)
    for i in range(len(df)):
        plt.text(df['price (USD)'][i]+2, df['employees_count'][i]+2, df['name'][i], fontsize=10)

    plt.title('기업 가치(주가) 및 고용 규모 사분면 분석', fontsize=16, pad=20)
    plt.xlabel('주가 (USD)', fontsize=12)
    plt.ylabel('고용 인원 (명)', fontsize=12)
    plt.grid(True, alpha=0.3)

    encoded_images.append(plt_to_base64())

    # 4. 직원 1인당 주가 기여도 (Efficiency)
    df['efficiency'] = df['price (USD)'] / df['employees_count'] * 1000 # 보기 편하게 배수 조절
    df_eff = df.sort_values('efficiency', ascending=False)

    plt.figure(figsize=(8, 5))
    sns.barplot(data=df_eff, x='efficiency', y='name', palette='plasma')

    plt.title('직원수 대비 주가 효율성 (알짜 기업 순위)', fontsize=15)
    plt.xlabel('주가/직원수 비율')
    encoded_images.append(plt_to_base64())

    return encoded_images

def plt_to_base64():
    """plt 이미지를 base64 스트링으로 변환"""
    img = io.BytesIO()
    plt.savefig(img, format='png', bbox_inches='tight')
    img.seek(0)
    plt.close()
    return base64.b64encode(img.getvalue()).decode('utf-8')

@app.route('/dashboard')
def dashboard():
    df = get_db_data()
    charts = create_plot(df)

    # 종합 평가를 위한 통계 계산
    summary = {
        'total_emp': df['employees_count'].sum(),
        'avg_price': round(df['price (USD)'].mean(), 2),
        'top_company': df.loc[df['employees_count'].idxmax(), 'name'],
        'top_price_company': df.loc[df['price (USD)'].idxmax(), 'name'],
        'top_country': df['country'].value_counts().idxmax()
    }
    
    return render_template('dashboard.html', charts=charts, summary=summary)

if __name__ == '__main__':
    app.run(debug=True)

