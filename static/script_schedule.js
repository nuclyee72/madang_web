document.addEventListener('DOMContentLoaded', function() {
  const calendarEl = document.getElementById('calendar');
  
  // Initialize FullCalendar
  const calendar = new FullCalendar.Calendar(calendarEl, {
    initialView: 'timeGridWeek',
    firstDay: 1,
    headerToolbar: {
      left: 'prev,next today',
      center: 'title',
      right: 'dayGridMonth,timeGridWeek'
    },
    locale: 'ko',
    buttonText: {
      today: '오늘',
      month: '월간',
      week: '주간',
      list: '목록'
    },
    slotMinTime: '09:00:00',
    expandRows: true,
    height: window.innerHeight - 150,
    events: async function(info, successCallback, failureCallback) {
      try {
        const response = await fetch('/schedule/api/events');
        const data = await response.json();
        
        // Transform backend data to FullCalendar event objects
        const events = data.map(item => ({
          id: item.id,
          title: item.title,
          start: item.time_start ? `${item.date}T${item.time_start}` : item.date,
          end: item.time_end ? `${item.date}T${item.time_end}` : null,
          allDay: !item.time_start,
          extendedProps: {
            location: item.location,
            description: item.description,
            requester: item.requester_name
          },
          backgroundColor: '#e4ebff',
          borderColor: '#4f7dff',
          textColor: '#1f3bb8'
        }));
        
        successCallback(events);
      } catch (error) {
        console.error("Error fetching events:", error);
        failureCallback(error);
      }
    },
    eventDidMount: function(info) {
      if (info.view.type === 'timeGridWeek' && info.event.extendedProps.location) {
        let titleEl = info.el.querySelector('.fc-event-title');
        if (titleEl) {
           titleEl.innerHTML += `<br/><span style="font-size: 0.85em; opacity: 0.9;">${info.event.extendedProps.location}</span>`;
        }
      }
    },
    eventClick: function(info) {
      document.getElementById('detailTitle').innerText = info.event.title;
      
      let timeStr = info.event.start.toLocaleDateString('ko-KR');
      if (!info.event.allDay) {
         timeStr += ' ' + info.event.start.toLocaleTimeString('ko-KR', {hour: '2-digit', minute:'2-digit'});
         if (info.event.end) {
             timeStr += ' ~ ' + info.event.end.toLocaleTimeString('ko-KR', {hour: '2-digit', minute:'2-digit'});
         }
      } else {
         timeStr += ' (종일)';
      }
      document.getElementById('detailTime').innerText = timeStr;
      
      const props = info.event.extendedProps;
      document.getElementById('detailLocation').innerText = props.location || '지정되지 않음';
      document.getElementById('detailRequester').innerText = props.requester || '-';
      document.getElementById('detailDescription').innerText = props.description || '상세 설명이 없습니다.';
      
      document.getElementById('detailModal').classList.add('active');
    }
  });

  calendar.render();

  // Handle window resize dynamically to prevent CSS calc collapse bugs
  window.addEventListener('resize', function() {
    calendar.setOption('height', window.innerHeight - 150);
  });
});

// Modal Logic
function openModal() {
  document.getElementById('requestModal').classList.add('active');
}

function closeModal() {
  document.getElementById('requestModal').classList.remove('active');
  document.getElementById('scheduleForm').reset();
}

function closeDetailModal() {
  document.getElementById('detailModal').classList.remove('active');
}

window.onclick = function(event) {
  const reqModal = document.getElementById('requestModal');
  const dtlModal = document.getElementById('detailModal');
  if (event.target === reqModal) {
    reqModal.classList.remove('active');
  }
  if (event.target === dtlModal) {
    dtlModal.classList.remove('active');
  }
}

// Form Submission
async function submitSchedule(e) {
  e.preventDefault();
  
  const form = e.target;
  const formData = new FormData(form);
  const data = {};
  formData.forEach((value, key) => {
    data[key] = value;
  });

  try {
    const response = await fetch('/schedule/api/request', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });

    let result;
    try {
      result = await response.json();
    } catch (parseErr) {
      throw new Error("서버에서 올바르지 않은 응답을 보냈습니다. (JSON 파싱 오류)");
    }
    
    if (response.ok) {
      alert("일정 신청이 완료되었습니다. 관리자 승인 후 캘린더에 표시됩니다.");
      closeModal();
    } else {
      alert("오류: " + (result.error || "알 수 없는 오류가 발생했습니다."));
    }
  } catch (err) {
    alert("오류가 발생했습니다: " + err.message);
    console.error(err);
  }
}
