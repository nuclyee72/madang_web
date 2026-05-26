document.addEventListener('DOMContentLoaded', () => {
  
  // 탭 전환 로직
  const switchBtns = document.querySelectorAll('.view-switch-btn');
  const views = {
    'global': document.getElementById('global-view'),
    'personal': document.getElementById('personal-view')
  };

  switchBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const targetView = btn.dataset.view;
      
      switchBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');

      Object.values(views).forEach(v => v.style.display = 'none');
      if (views[targetView]) {
        views[targetView].style.display = 'block';
      }
    });
  });

  // Chart 인스턴스 저장용 (초기화용)
  let globalTimeChart, globalMonthChart, globalWeekdayChart;
  let personalRadarChart;

  // 전체 통계 로드
  function loadGlobalSummary() {
    fetch('/mahjong_rating/review/api/summary/global')
      .then(r => r.json())
      .then(data => {
        if (!data.ok) return console.error(data.error);

        // 기본 통계 세팅
        document.getElementById('global-total-games').textContent = data.total_games;
        document.getElementById('global-total-players').textContent = data.total_players;
        
        const archives = data.archive_stats || [];
        let compareText = "";
        if (archives.length > 0) {
          compareText = archives.map(arch => {
            const diff = data.total_games - arch.total_games;
            const pct = Math.abs(diff) / arch.total_games * 100;
            if (diff > 0) return `[${arch.name}] 대비 ${pct.toFixed(1)}% 🔼`;
            else if (diff < 0) return `[${arch.name}] 대비 ${pct.toFixed(1)}% 🔽`;
            else return `[${arch.name}] 와 동일`;
          }).join(" / ");
        } else {
          compareText = "비교 대상 아카이브 없음";
        }
        document.getElementById('global-prev-games-compare').textContent = compareText;

        document.getElementById('global-exam-avg').textContent = data.exam_stats.avg_exam;
        document.getElementById('global-normal-avg').textContent = data.exam_stats.avg_normal;

        // 차트 렌더링
        renderGlobalCharts(data);
      });
  }

  function renderGlobalCharts(data) {
    Chart.defaults.font.family = "'GyeonggiBatang', sans-serif";

    // 1. 시간대 파이 차트
    if(globalTimeChart) globalTimeChart.destroy();
    const ctxTime = document.getElementById('global-time-chart').getContext('2d');
    globalTimeChart = new Chart(ctxTime, {
      type: 'doughnut',
      data: {
        labels: ['정상 시간대 (06~24)', '밤샘 마작 (00~06)'],
        datasets: [{
          data: [data.time_distribution.normal, data.time_distribution.late_night],
          backgroundColor: ['#4dd2a6', '#2c3e50']
        }]
      },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom' } } }
    });

    // 2. 월별 트렌드 바 차트
    if(globalMonthChart) globalMonthChart.destroy();
    const months = Object.keys(data.month_counts).sort();
    const monthCounts = months.map(m => data.month_counts[m]);
    
    const ctxMonth = document.getElementById('global-month-chart').getContext('2d');
    globalMonthChart = new Chart(ctxMonth, {
      type: 'bar',
      data: {
        labels: months,
        datasets: [{
          label: '월별 대국 수',
          data: monthCounts,
          backgroundColor: '#4f7dff'
        }]
      },
      options: { responsive: true, maintainAspectRatio: false }
    });

    // 3. 요일별 트렌드 바 차트
    if(globalWeekdayChart) globalWeekdayChart.destroy();
    const weekLabels = ['월', '화', '수', '목', '금', '토', '일'];
    const ctxWeekday = document.getElementById('global-weekday-chart').getContext('2d');
    globalWeekdayChart = new Chart(ctxWeekday, {
      type: 'bar',
      data: {
        labels: weekLabels,
        datasets: [{
          label: '요일별 대국 수',
          data: data.day_of_week,
          backgroundColor: '#ff6b81'
        }]
      },
      options: { responsive: true, maintainAspectRatio: false }
    });
  }

  // 개인별 통계 로드
  const searchBtn = document.getElementById('personal-search-btn');
  const searchInput = document.getElementById('personal-player-input');
  
  searchInput.addEventListener('keypress', (e) => {
    if(e.key === 'Enter') searchBtn.click();
  });

  searchBtn.addEventListener('click', () => {
    const name = searchInput.value.trim();
    const err = document.getElementById('personal-error-msg');
    if (!name) return;
    
    fetch(`/mahjong_rating/review/api/summary/player/${name}`)
      .then(r => r.json())
      .then(data => {
        if (!data.ok) {
          err.textContent = data.error;
          err.style.display = 'block';
          document.getElementById('personal-content-left').style.display = 'none';
          document.getElementById('personal-content-right').style.display = 'none';
          return;
        }
        err.style.display = 'none';
        
        // 데이터 채우기
        document.getElementById('p-total-games').textContent = data.total_games;
        document.getElementById('p-max-score').textContent = data.max_score > -90000 ? data.max_score : '-';
        document.getElementById('p-attendance').textContent = data.max_attendance_streak + '일';
        document.getElementById('p-bankrupt').textContent = data.bankrupt_rate + '%';
        
        if (data.most_played_date) {
          document.getElementById('p-most-played-date').textContent = `가장 많이 플레이한 날: ${data.most_played_date} (${data.most_played_date_count}판)`;
        } else {
          document.getElementById('p-most-played-date').textContent = '';
        }

        document.getElementById('p-streak-1st').textContent = data.streaks.max_1st + '연속';
        document.getElementById('p-streak-yonde').textContent = data.streaks.max_yonde + '연속';
        document.getElementById('p-streak-avoid4').textContent = data.streaks.max_avoid_4th + '연속';
        document.getElementById('p-streak-4th').textContent = data.streaks.max_4th + '연속';

        // 상성 분석 텍스트
        if(data.best_opponent) {
          document.getElementById('p-best-opponent').textContent = data.best_opponent.name;
          document.getElementById('p-best-gap').textContent = `나의 평균 ${data.best_opponent.my_avg_rank}등 / 상대 평균 ${data.best_opponent.their_avg_rank}등`;
        } else {
          document.getElementById('p-best-opponent').textContent = "데이터 부족";
          document.getElementById('p-best-gap').textContent = "-";
        }

        if(data.worst_opponent) {
          document.getElementById('p-worst-opponent').textContent = data.worst_opponent.name;
          document.getElementById('p-worst-gap').textContent = `나의 평균 ${data.worst_opponent.my_avg_rank}등 / 상대 평균 ${data.worst_opponent.their_avg_rank}등`;
        } else {
          document.getElementById('p-worst-opponent').textContent = "데이터 부족";
          document.getElementById('p-worst-gap').textContent = "-";
        }

        // 같이 많이 한 사람 테이블
        const tbody = document.getElementById('p-co-players-tbody');
        tbody.innerHTML = '';
        data.top_co_players.forEach(p => {
          const tr = document.createElement('tr');
          tr.innerHTML = `
            <td>${p.name}</td>
            <td>${p.games}</td>
            <td>${p.my_avg_rank}</td>
            <td>${p.their_avg_rank}</td>
          `;
          tbody.appendChild(tr);
        });

        // 뱃지 렌더링
        const bc = document.getElementById('p-badges-container');
        bc.innerHTML = '';
        if(data.badges && data.badges.length > 0) {
          data.badges.forEach(b => {
            const span = document.createElement('span');
            span.style.padding = '4px 8px';
            span.style.background = '#eee';
            span.style.borderRadius = '12px';
            span.style.fontSize = '12px';
            span.style.border = '1px solid #ddd';
            span.title = b.description;
            span.textContent = `${b.name} (${b.grade})`;
            bc.appendChild(span);
          });
        } else {
          bc.innerHTML = '<span style="font-size:12px; color:#999;">뱃지 없음</span>';
        }

        // 레이더 차트 렌더링
        renderPersonalRadar(data);

        // 패널 표시
        document.getElementById('personal-content-left').style.display = 'block';
        document.getElementById('personal-content-right').style.display = 'block';
      });
  });

  function renderPersonalRadar(data) {
    if(personalRadarChart) personalRadarChart.destroy();
    
    // 플레이 횟수 기준 탑5 유저를 방사형 그래프로
    const labels = data.top_co_players.map(p => p.name);
    const chartData = data.top_co_players.map(p => p.games);
    
    if (labels.length === 0) return;

    const ctx = document.getElementById('personal-radar-chart').getContext('2d');
    personalRadarChart = new Chart(ctx, {
      type: 'radar',
      data: {
        labels: labels,
        datasets: [{
          label: '같이 한 판수',
          data: chartData,
          backgroundColor: 'rgba(79, 125, 255, 0.2)',
          borderColor: 'rgba(79, 125, 255, 1)',
          pointBackgroundColor: 'rgba(79, 125, 255, 1)',
        }]
      },
      options: { 
        responsive: true, 
        maintainAspectRatio: false,
        scales: {
          r: {
            beginAtZero: true,
            ticks: { stepSize: Math.ceil(Math.max(...chartData)/5) || 1 }
          }
        }
      }
    });
  }

  // 초기 실행
  loadGlobalSummary();
});
