var BOOT = window.ADMIN_BOOTSTRAP || {};
var ROOMS = BOOT.rooms || {};
var _clientRooms = BOOT.rooms || {};
var GLOBAL_CALS = BOOT.globalCalendars || [];

// One-time status messages come in via query params; remove them after render
// so refreshes don't keep showing stale success/error banners.
(function(){
  var url = new URL(window.location.href);
  var transientKeys = ['dropbox', 'dropbox_error', 'restored', 'restore_error'];
  var changed = false;
  transientKeys.forEach(function(key){
    if(url.searchParams.has(key)){
      url.searchParams.delete(key);
      changed = true;
    }
  });
  if(changed){
    var next = url.pathname + (url.search ? url.search : '') + url.hash;
    window.history.replaceState({}, document.title, next);
  }
})();

function _fetch(url, opts){
  return fetch(url, opts || {});
}

function closeModal(id){ document.getElementById(id).classList.remove('open'); }
document.querySelectorAll('.modal-backdrop').forEach(function(el){
  el.addEventListener('click',function(e){ if(e.target===el) el.classList.remove('open'); });
});

document.getElementById('new-startHour').value = 8;
document.getElementById('new-endHour').value = 22;

function openEdit(rid){
  var r = ROOMS[rid];
  document.getElementById('edit-title-label').textContent = 'Edit: ' + r.title;
  document.getElementById('edit-form').action = '/admin/room/' + rid + '/edit';
  document.getElementById('e-title').value = r.title || '';
  document.getElementById('e-ical').value = r.icalUrl || '';
  document.getElementById('e-refresh').value = r.refresh || 5;
  document.getElementById('e-slideshow').checked = !!r.showSlideshow;
  document.getElementById('e-startHour').value = r.startHour || 8;
  document.getElementById('e-endHour').value = r.endHour || 22;
  document.getElementById('modal-edit').classList.add('open');
}

function showToast(msg){
  var t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(function(){ t.classList.remove('show'); }, 2500);
}

var PROPARED = {
  rows: ['All Calendar','Misc','Dance Shows','UG Shows','REP Shows'],
  cols: ['Red','Orange','Amber','Yellow','Lime','Yellow-Green','Green','Teal','Blue','Indigo','Purple','Pink','Gray'],
  colors: [
    ['#FFF1F0','#FFF2E8','#FFF7E6','#FFFBE6','#FEFFE6','#FCFFE6','#F6FFED','#E6FFFB','#E6F7FF','#F0F5FF','#FAF0FF','#FFF0F6','#FFFFFF'],
    ['#FFCCC7','#FFD8BF','#FFE7BA','#FFF1B8','#FFFFB8','#F4FFB8','#D9F7BE','#B5F5EC','#BAE7FF','#D6E4FF','#EFDBFF','#FFD6E7','#FAFAFA'],
    ['#FFA39E','#FFBB96','#FFD591','#FFE58F','#FFFB8F','#EAFF8F','#B7EB8F','#87E8DE','#91D5FF','#ADC6FF','#D3ADF7','#FFADD2','#F5F5F5'],
    ['#FF7875','#FF9C6E','#FFC069','#FFD666','#FFF566','#D3F261','#95DE64','#5CDBD3','#69C0FF','#85A5FF','#B37FEB','#FF85C0','#F0F0F0'],
    ['#FF4D4F','#FF7A45','#FFA940','#FFC53D','#FFEC3D','#BAE637','#73D13D','#36CFC9','#40A9FF','#597EF7','#9254DE','#F759AB','#D9D9D9']
  ]
};

var _pickerTarget = null;
var _pickerEl = null;

function _buildPicker(){
  if(_pickerEl) return;
  var el = document.createElement('div');
  el.className = 'propared-picker';
  el.id = 'propared-picker';
  var title = document.createElement('div');
  title.className = 'propared-picker-title';
  title.textContent = 'Propared Colours';
  el.appendChild(title);
  var sections = [[0,5],[5,10],[10,13]];
  var wrapper = document.createElement('div');
  wrapper.style.cssText = 'display:flex;gap:8px;align-items:flex-start';
  sections.forEach(function(range){
    var section = document.createElement('div');
    section.style.cssText = 'display:flex;flex-direction:column;gap:4px';
    PROPARED.rows.forEach(function(rowName, ri){
      var rowDiv = document.createElement('div');
      rowDiv.style.cssText = 'display:flex;gap:4px';
      PROPARED.colors[ri].slice(range[0], range[1]).forEach(function(color){
        var sw = document.createElement('div');
        sw.className = 'propared-swatch';
        sw.style.background = color;
        sw.addEventListener('click', function(){ selectProparedColor(color); });
        rowDiv.appendChild(sw);
      });
      section.appendChild(rowDiv);
    });
    wrapper.appendChild(section);
  });
  el.appendChild(wrapper);
  var close = document.createElement('div');
  close.className = 'propared-close';
  close.textContent = '× Close';
  close.addEventListener('click', closeProparedPicker);
  el.appendChild(close);
  document.body.appendChild(el);
  _pickerEl = el;
  document.addEventListener('click', function(e){
    if(_pickerEl && _pickerEl.classList.contains('open') &&
       !_pickerEl.contains(e.target) && e.target !== _pickerTarget){
      closeProparedPicker();
    }
  });
}

function openProparedPicker(swatchEl){
  _buildPicker();
  _pickerTarget = swatchEl;
  var rect = swatchEl.getBoundingClientRect();
  var currentColor = swatchEl.dataset.color || swatchEl.style.background;
  _pickerEl.style.left = Math.min(rect.left, window.innerWidth - 380) + 'px';
  _pickerEl.style.top = (rect.bottom + 6) + 'px';
  _pickerEl.querySelectorAll('.propared-swatch').forEach(function(s){
    s.classList.toggle('selected', s.style.background === currentColor ||
      s.style.backgroundColor === swatchEl.style.backgroundColor);
  });
  _pickerEl.classList.add('open');
}

function selectProparedColor(color){
  if(!_pickerTarget) return;
  _pickerTarget.style.background = color;
  _pickerTarget.dataset.color = color;
  closeProparedPicker();
}

function closeProparedPicker(){
  if(_pickerEl) _pickerEl.classList.remove('open');
  _pickerTarget = null;
}

function swatchChange(input){ input.parentElement.style.background = input.value; }
function tagNameChange(input){ input.closest('.tag-row').dataset.tag = input.value; }
function removeTag(btn){ btn.closest('.tag-row').remove(); }

function addTag(){
  var row = document.createElement('div');
  row.className = 'tag-row';
  row.dataset.tag = '';
  row.innerHTML = '<div class="swatch" style="background:#2563c7" data-color="#2563c7" onclick="openProparedPicker(this)"></div>'
    + '<div class="tag-inputs"><input class="tag-input" type="text" value="" placeholder="TagKey" oninput="tagNameChange(this)">'
    + '<input class="tag-input fullname" type="text" value="" placeholder="e.g. Spring Dance Concert"></div>'
    + '<button class="tag-remove" onclick="removeTag(this)">&#215;</button>';
  document.getElementById('tag-grid').appendChild(row);
}

function saveTagColors(){
  var result = {};
  document.querySelectorAll('.tag-row').forEach(function(row){
    var inputs = row.querySelectorAll('input[type=text]');
    var key = inputs[0].value.trim();
    var fullName = inputs[1].value.trim();
    var sw = row.querySelector('.swatch');
    var color = (sw && sw.dataset.color) ? sw.dataset.color : '#2563c7';
    if(key) result[key] = {color: color, fullName: fullName};
  });
  _fetch('/api/tag-colors', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify(result)
  }).then(function(r){ if(r.ok) showToast('Tag colors saved!'); });
}

function loadBackupList(){
  var el = document.getElementById('backup-list');
  el.textContent = 'Loading…';
  _fetch('/admin/backup/list').then(function(r){ return r.json(); }).then(function(list){
    if(!list.length){ el.innerHTML = '<em>No saved backups yet.</em>'; return; }
    var html = '<div style="display:flex;flex-direction:column;gap:6px">';
    list.forEach(function(b){
      html += '<div style="display:flex;align-items:center;gap:10px;background:var(--s2);'
        + 'border:1px solid var(--border);border-radius:6px;padding:8px 12px">'
        + '<div style="flex:1;overflow:hidden">'
        + '<div style="font-family:DM Mono,monospace;font-size:11px;color:var(--text);'
        + 'white-space:nowrap;overflow:hidden;text-overflow:ellipsis">' + b.name + '</div>'
        + '<div style="font-size:10px;color:var(--muted);margin-top:2px">'
        + new Date(b.mtime*1000).toLocaleString() + '&nbsp;&middot;&nbsp;' + Math.round(b.size/1024) + ' KB</div>'
        + '</div>'
        + '<a href="/admin/backup/download/' + encodeURIComponent(b.name) + '" class="btn btn-ghost btn-sm">&#11015;</a>'
        + '<form method="POST" action="/admin/backup/delete/' + encodeURIComponent(b.name) + '" '
        + 'onsubmit="return confirm(\'Delete this backup?\')" style="margin:0">'
        + '<button type="submit" class="btn btn-danger btn-sm">&#215;</button></form>'
        + '</div>';
    });
    el.innerHTML = html + '</div>';
  }).catch(function(){ el.innerHTML = '<em>Could not load backup list.</em>'; });
}
loadBackupList();

function loadClients(){
  var el = document.getElementById('client-list');
  _fetch('/admin/clients').then(function(r){ return r.json(); }).then(function(data){
    if(!data.length){
      el.innerHTML = '<div style="font-size:12px;color:var(--muted);font-style:italic">No clients registered yet. Boot a Pi to register it automatically.</div>';
      return;
    }
    el.innerHTML = '';
    var header = document.createElement('div');
    header.style.cssText = 'display:grid;grid-template-columns:150px 110px 70px 1fr 110px 110px 110px 160px;gap:8px;padding:0 10px 6px;font-size:10px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:var(--dim)';
    header.innerHTML = '<span>Hostname</span><span>IP</span><span>Status</span><span>Assigned Room</span><span>Screen On</span><span>Screen Off</span><span>Schedule</span><span>Actions</span>';
    el.appendChild(header);

    data.forEach(function(c){
      var row = document.createElement('div');
      row.style.cssText = 'display:grid;grid-template-columns:150px 110px 70px 1fr 110px 110px 110px 160px;gap:8px;align-items:center;background:var(--s2);border:1px solid var(--border);border-radius:7px;padding:10px;margin-bottom:6px';
      var hn = document.createElement('div');
      hn.style.cssText = 'font-size:13px;font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap';
      hn.textContent = c.hostname;
      row.appendChild(hn);

      var ip = document.createElement('a');
      ip.href = 'ssh://screenadmin@' + c.ip;
      ip.style.cssText = 'font-family:DM Mono,monospace;font-size:11px;color:var(--accent);text-decoration:none;cursor:pointer';
      ip.title = 'Open SSH session to ' + c.ip;
      ip.textContent = c.ip;
      row.appendChild(ip);

      var badge = document.createElement('div');
      badge.innerHTML = c.online
        ? '<span class="pill pill-green">&#9679; Online</span>'
        : '<span class="pill pill-red">&#9675; Offline</span>';
      row.appendChild(badge);

      var sel = document.createElement('select');
      sel.className = 'fi';
      sel.style.cssText = 'font-size:12px;padding:4px 8px';
      var opt0 = document.createElement('option');
      opt0.value = '';
      opt0.textContent = '— Unassigned —';
      sel.appendChild(opt0);
      var optD = document.createElement('option');
      optD.value = '__dashboard__';
      optD.textContent = 'Dashboard';
      if(c.assigned_room === '__dashboard__') optD.selected = true;
      sel.appendChild(optD);
      Object.entries(_clientRooms).forEach(function(entry){
        var opt = document.createElement('option');
        opt.value = entry[0];
        opt.textContent = entry[1].title;
        if(c.assigned_room === entry[0]) opt.selected = true;
        sel.appendChild(opt);
      });
      row.appendChild(sel);

      var onInput = document.createElement('input');
      onInput.className = 'fi';
      onInput.type = 'time';
      onInput.value = c.screenOn || '08:00';
      onInput.style.cssText = 'font-size:12px;padding:4px 8px';
      row.appendChild(onInput);

      var offInput = document.createElement('input');
      offInput.className = 'fi';
      offInput.type = 'time';
      offInput.value = c.screenOff || '22:00';
      offInput.style.cssText = 'font-size:12px;padding:4px 8px';
      row.appendChild(offInput);

      var schedWrap = document.createElement('div');
      schedWrap.style.cssText = 'display:flex;align-items:center;gap:6px';
      var schedCb = document.createElement('input');
      schedCb.type = 'checkbox';
      schedCb.checked = !!c.scheduleEnabled;
      schedCb.style.cssText = 'width:15px;height:15px;cursor:pointer';
      var schedLbl = document.createElement('span');
      schedLbl.style.cssText = 'font-size:11px;color:var(--muted)';
      schedLbl.textContent = 'Enabled';
      schedWrap.appendChild(schedCb);
      schedWrap.appendChild(schedLbl);
      row.appendChild(schedWrap);

      var btns = document.createElement('div');
      btns.style.cssText = 'display:flex;gap:4px;align-items:center;flex-wrap:wrap';
      var saveBtn = document.createElement('button');
      saveBtn.className = 'btn btn-primary btn-sm';
      saveBtn.textContent = 'Save';
      saveBtn.addEventListener('click', function(){
        _fetch('/admin/client/' + c.client_id + '/assign', {
          method: 'POST',
          headers: {'Content-Type':'application/json'},
          body: JSON.stringify({
            assigned_room: sel.value,
            screenOn: onInput.value,
            screenOff: offInput.value,
            scheduleEnabled: schedCb.checked
          })
        }).then(function(r){ if(r.ok) showToast('Client updated!'); });
      });
      var delBtn = document.createElement('button');
      delBtn.className = 'btn btn-danger btn-sm';
      delBtn.textContent = '✕';
      delBtn.addEventListener('click', function(){
        if(!confirm('Remove this client record?')) return;
        _fetch('/admin/client/' + c.client_id + '/delete', {method:'POST'})
          .then(function(r){ if(r.ok){ loadClients(); showToast('Client removed.'); } });
      });
      var restartBtn = document.createElement('button');
      restartBtn.className = 'btn btn-ghost btn-sm';
      restartBtn.textContent = 'Restart kiosk';
      if(c.pending_command && c.pending_command.command === 'restart_kiosk'){
        restartBtn.disabled = true;
        restartBtn.textContent = 'Restart queued';
      }
      restartBtn.addEventListener('click', function(){
        if(!confirm('Queue a kiosk restart for ' + c.hostname + '?')) return;
        _fetch('/admin/client/' + c.client_id + '/command', {
          method: 'POST',
          headers: {'Content-Type':'application/json'},
          body: JSON.stringify({command: 'restart_kiosk'})
        }).then(function(r){
          if(r.ok){
            showToast('Kiosk restart queued.');
            loadClients();
          }
        });
      });
      btns.appendChild(saveBtn);
      btns.appendChild(restartBtn);
      btns.appendChild(delBtn);
      row.appendChild(btns);
      el.appendChild(row);
    });
  }).catch(function(){
    document.getElementById('client-list').innerHTML = '<div style="font-size:12px;color:#f87171">Could not load clients.</div>';
  });
}
loadClients();
setInterval(loadClients, 30000);

function renderGlobalCals(){
  var list = document.getElementById('global-cal-list');
  list.innerHTML = '';
  GLOBAL_CALS.forEach(function(gc, i){
    list.appendChild(makeGlobalCalRow(gc, i));
  });
  document.getElementById('add-global-btn').style.display =
    GLOBAL_CALS.length >= 3 ? 'none' : '';
}

function makeGlobalCalRow(gc, i){
  var row = document.createElement('div');
  row.style.cssText = 'display:flex;align-items:center;gap:8px;background:var(--s2);border:1px solid var(--border);border-radius:7px;padding:10px 12px';

  var sw = document.createElement('div');
  sw.className = 'swatch';
  sw.style.background = gc.color || '#555555';
  sw.dataset.color = gc.color || '#555555';
  sw.addEventListener('click', function(){ openProparedPicker(sw); });
  row.appendChild(sw);

  var nameInput = document.createElement('input');
  nameInput.className = 'fi';
  nameInput.type = 'text';
  nameInput.placeholder = 'Calendar name (e.g. University Holidays)';
  nameInput.value = gc.name || '';
  nameInput.style.cssText = 'flex:1;font-size:12px;padding:5px 9px';
  nameInput.addEventListener('input', function(){ updateGlobalCal(i, 'name', this.value); });
  row.appendChild(nameInput);

  var urlInput = document.createElement('input');
  urlInput.className = 'fi';
  urlInput.type = 'text';
  urlInput.placeholder = 'iCal URL (https://...)';
  urlInput.value = gc.url || '';
  urlInput.style.cssText = 'flex:2;font-size:12px;padding:5px 9px';
  urlInput.addEventListener('input', function(){ updateGlobalCal(i, 'url', this.value); });
  row.appendChild(urlInput);

  var btn = document.createElement('button');
  btn.className = 'btn btn-danger btn-sm';
  btn.textContent = '×';
  btn.addEventListener('click', function(){ removeGlobalCal(i); });
  row.appendChild(btn);

  return row;
}

function addGlobalCal(){
  if(GLOBAL_CALS.length >= 3) return;
  GLOBAL_CALS.push({id: 'global_' + Date.now(), name: '', url: '', color: '#555555'});
  renderGlobalCals();
}

function removeGlobalCal(i){
  GLOBAL_CALS.splice(i, 1);
  renderGlobalCals();
}

function updateGlobalCal(i, field, val){
  if(GLOBAL_CALS[i]) GLOBAL_CALS[i][field] = val;
}

function saveGlobalCals(){
  var rows = document.getElementById('global-cal-list').children;
  Array.from(rows).forEach(function(row, i){
    var sw = row.querySelector('.swatch');
    if(sw && sw.dataset.color && GLOBAL_CALS[i]) GLOBAL_CALS[i].color = sw.dataset.color;
    if(GLOBAL_CALS[i] && !GLOBAL_CALS[i].id) GLOBAL_CALS[i].id = 'global_' + Date.now() + '_' + i;
  });
  _fetch('/admin/global-calendars', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({globalCalendars: GLOBAL_CALS})
  }).then(function(r){ if(r.ok) showToast('Global calendars saved!'); });
}

renderGlobalCals();

(function(){
  var list = document.getElementById('dash-room-list');
  if(!list) return;
  var dragging = null;
  list.addEventListener('dragstart', function(e){
    dragging = e.target.closest('.dash-row');
    if(dragging){ dragging.style.opacity = '.4'; e.dataTransfer.effectAllowed = 'move'; }
  });
  list.addEventListener('dragend', function(){
    if(dragging) dragging.style.opacity = '';
    dragging = null;
    list.querySelectorAll('.dash-row').forEach(function(r){ r.classList.remove('drag-over'); });
  });
  list.addEventListener('dragover', function(e){
    e.preventDefault();
    var target = e.target.closest('.dash-row');
    if(!target || target === dragging) return;
    list.querySelectorAll('.dash-row').forEach(function(r){ r.classList.remove('drag-over'); });
    target.classList.add('drag-over');
    if(e.clientY > target.getBoundingClientRect().top + target.offsetHeight / 2) list.insertBefore(dragging, target.nextSibling);
    else list.insertBefore(dragging, target);
  });
  list.addEventListener('dragleave', function(e){
    var t = e.target.closest('.dash-row');
    if(t) t.classList.remove('drag-over');
  });
  list.addEventListener('drop', function(e){ e.preventDefault(); });

  var form = document.getElementById('dash-form');
  if(form) {
    form.addEventListener('submit', function() {
      form.querySelectorAll('input[name="dashboardRooms"]').forEach(function(el){ el.disabled = true; });
      list.querySelectorAll('.dash-row').forEach(function(row) {
        var cb = row.querySelector('input[type="checkbox"]');
        if(cb && cb.checked) {
          var hidden = document.createElement('input');
          hidden.type = 'hidden';
          hidden.name = 'dashboardRooms';
          hidden.value = row.dataset.rid;
          form.appendChild(hidden);
        }
      });
    });
  }
})();
