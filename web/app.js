'use strict';
const $ = id => document.getElementById(id);
let csrf = '', zone = 'Europe/Moscow', vehicles = [], map, layers, car, latest, report;
let mode = 'live', generation = 0, busy = false, receivedAt = 0, needFit = true;
let canManage = false, sessionUser = '';
let favorite = null, favoriteMarker = null, pickingStop = false, pendingStop = null;
const fmtTime = value => value ? new Intl.DateTimeFormat('ru-RU', {timeZone: zone, hour: '2-digit', minute: '2-digit'}).format(new Date(value)) : '—';
const duration = seconds => seconds == null ? '—' : seconds < 60 ? `${Math.floor(seconds)} с` : seconds < 3600 ? `${Math.floor(seconds / 60)} мин` : `${Math.floor(seconds / 3600)} ч ${Math.floor(seconds % 3600 / 60)} мин`;
const today = () => new Intl.DateTimeFormat('en-CA', {timeZone: zone, year:'numeric', month:'2-digit', day:'2-digit'}).format(new Date());
const vehicleId = () => $('vehicle-select').value;
const text = (id, value) => { $(id).textContent = value; };

async function api(path, options = {}) {
  const response = await fetch('/api/v1' + path, {...options, credentials: 'same-origin', cache: 'no-store',
    headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf, ...options.headers}, signal: AbortSignal.timeout(12000)});
  if (!response.ok) {
    if (response.status === 401 && path !== '/auth/login') showLogin();
    const messages = {401: 'Неверный логин или пароль.', 403: 'Действие недоступно для этого аккаунта или сессия устарела.',
      429: 'Слишком много попыток входа. Попробуйте через 15 минут.', 422: 'Проверьте введённые данные.',
      409: 'Этот IMEI уже зарегистрирован, в том числе среди отключённых устройств.'};
    throw new Error(messages[response.status] || `Ошибка сервера (${response.status}). Попробуйте ещё раз.`);
  }
  return response.status === 204 ? null : response.json();
}

function showLogin() {
  resetPassword(); $('login-password').value = ''; sessionUser = ''; clearFavorite();
  $('install-dialog').close(); $('car-button').disabled = true;
  canManage = false; $('manage-button').hidden = true; $('add-first').hidden = true;
  generation++; csrf = ''; vehicles = []; latest = report = null; receivedAt = 0;
  $('dashboard').hidden = true; $('login-view').hidden = false;
  $('manage-dialog').close(); $('device-token').value = ''; $('token-result').hidden = true;
  $('stops-list').replaceChildren(); layers?.clearLayers();
  if (car) {car.remove(); car = null;}
}

function initMap() {
  if (map) {setTimeout(() => map.invalidateSize(), 0); return;}
  if (!window.L) throw new Error('Библиотека карты не загружена. Выполните npm install и npm run vendor в папке web.');
  map = L.map('map', {zoomControl: false}).setView([55.75, 37.61], 10);
  map.attributionControl.setPrefix('<a href="https://leafletjs.com" title="Библиотека интерактивных карт">Leaflet</a>');
  L.control.zoom({position:'bottomright'}).addTo(map);
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {maxZoom:19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>'}).addTo(map);
  layers = L.featureGroup().addTo(map);
  map.on('dragstart', () => {needFit = false;});
  map.on('zoomend', sizeCarMarker);
  map.on('click', chooseStopPoint);
}

function sizeCarMarker() {
  const art = car?.getElement()?.querySelector('.car-art');
  if (!art || !map) return;
  // Small on a city overview, detailed nearby; the transparent tap target stays 44px.
  const height = Math.max(20, Math.min(40, 20 + (map.getZoom() - 11) * 3));
  art.style.height = `${height}px`;
  art.style.width = 'auto';
}

async function loadVehicles() {
  vehicles = await api('/vehicles');
  const old = vehicleId();
  $('vehicle-select').replaceChildren(...vehicles.map(v => new Option(v.name, v.id)));
  if (vehicles.some(v => String(v.id) === old)) $('vehicle-select').value = old;
  $('empty-state').hidden = vehicles.length > 0; $('fleet-content').hidden = vehicles.length === 0;
  $('device-form').hidden = vehicles.length === 0;
  $('hardware-form').hidden = vehicles.length === 0;
  if (!vehicles.length) text('sync-label', canManage ? 'Сервер доступен · добавьте автомобиль' : 'Сервер доступен · ожидаем автомобиль');
  if (vehicles.length) initMap();
}

async function enter(session) {
  sessionUser = session.username; resetPassword(); $('login-password').value = '';
  canManage = session.role === 'owner';
  $('manage-button').hidden = !canManage; $('add-first').hidden = !canManage;
  text('access-label', canManage ? 'Владелец' : 'Только просмотр');
  $('access-label').hidden = canManage;
  text('empty-title', canManage ? 'Добавьте первый автомобиль' : 'Автомобилей пока нет');
  text('empty-description', canManage ? 'Зарегистрируйте машину, получите токен и введите его на Android-телефоне.' : 'Автомобиль появится здесь после добавления владельцем.');
  csrf = session.csrf_token; zone = session.timezone; generation++;
  $('login-view').hidden = true; $('dashboard').hidden = false;
  $('history-date').value = today(); $('history-date').max = today();
  text('timezone', `Часовой пояс: ${zone}`);
  await loadVehicles(); loadFavorite(); await refresh();
}

function warn(message) {text('error-banner', message); $('error-banner').hidden = !message;}

async function refresh() {
  if (!csrf || !vehicleId() || busy) return;
  busy = true;
  const current = generation, id = vehicleId(), date = $('history-date').value || today();
  try {
    const result = await Promise.all([api(`/vehicles/${id}/latest`), api(`/vehicles/${id}/route?date=${encodeURIComponent(date)}`)]);
    if (current !== generation) return;
    [latest, report] = result; receivedAt = Date.now();
    warn(''); text('sync-label', `Обновлено в ${fmtTime(receivedAt)}`);
    text('vehicle-plate', vehicles.find(v => String(v.id) === id)?.plate || 'Служебный автомобиль');
    $('car-button').disabled = !latest.point;
    renderStats(); renderMap(); renderLive();
  } catch (e) {
    if (current === generation && csrf) {warn(e.name === 'TimeoutError' || e instanceof TypeError ? 'Сервер недоступен. Показаны последние полученные данные.' : e.message); text('sync-label', 'Не удалось обновить');}
  } finally {busy = false; if (current !== generation && csrf) refresh();}
}

function renderLive() {
  if (!latest || !csrf) return;
  const elapsed = (Date.now() - receivedAt) / 1000;
  const s = trackerState(latest, elapsed), age = s.age;
  const p = latest.point;
  const h = latest.device_health;
  const hardware = latest.device_kind === "navtelecom";
  let label = s.gpsFresh ? p?.speed > 3 ? 'В движении' : 'На месте' : 'Телефон на связи · нет свежего GPS';
  if (s.healthFresh && h.location_permission === false) label = 'Телефон на связи · нет разрешения GPS';
  else if (s.healthFresh && !h.gps_enabled) label = 'Телефон на связи · GPS выключен';
  else if (!s.gpsFresh && s.healthFresh && h.gps_age_seconds != null && h.gps_age_seconds + h.age_seconds + elapsed < latest.stale_seconds && h.queue_count > 0) label = 'Телефон на связи · точки ожидают отправки';
  if (s.connection !== 'fresh') label = s.contactAge == null ? 'Телефон ещё не подключён' : s.connection === 'offline' ? `Нет связи ${duration(s.contactAge)}` : `Давно нет связи · ${duration(s.contactAge)}`;
  if (!s.siteFresh) label = 'Сайт не получает обновления';
  $('connection-status').className = 'status ' + s.state;
  text('connection-status', label);
  text('last-signal', p ? `${fmtTime(p.gps_timestamp)} · ${duration(age)} назад` : 'Ещё не поступала');
  text('last-contact', latest.last_contact ? `Связь с телефоном: ${fmtTime(latest.last_contact)} · ${duration(s.contactAge)} назад` : 'Телефон ещё не подключён');
  text('speed', s.speed != null ? Math.round(s.speed) : '—');
  text('battery', s.battery?.battery_level != null ? `${s.battery.battery_level}%` : '—');
  $('battery-bar').style.width = `${s.battery?.battery_level ?? 0}%`;
  text('charging', !s.battery ? 'Нет сигнала от телефона' : `${s.battery.charging == null ? 'Зарядка неизвестна' : s.battery.charging ? 'Подключён к зарядке' : 'Работает от батареи'}${!s.batteryFresh ? ' · последний сигнал' : ''}`);
  let diagnostics = h ? `Трекер ${h.app_version} · очередь ${h.queue_count}${!s.healthFresh ? ' · данные устарели' : ''}` : 'Для проверки связи без GPS обновите трекер до 1.0.2';
  if (s.healthFresh && !hardware && !h.background_permission) diagnostics += '\nРазрешите геолокацию «Всегда»';
  if (s.healthFresh && !hardware && !h.battery_optimization_exempt) diagnostics += '\nОтключите экономию батареи для трекера';
  if (s.batteryFresh && s.battery?.battery_level != null && s.battery.battery_level <= 20 && s.battery.charging === false) diagnostics += '\nНизкий заряд — подключите питание';
  if (hardware) {
    label = label.replaceAll('Телефон', 'Трекер').replaceAll('телефоном', 'трекером');
    text('connection-status', label);
    text('last-contact', latest.last_contact ? `Связь с трекером: ${fmtTime(latest.last_contact)} · ${duration(s.contactAge)} назад` : 'Трекер ещё не подключён');
    text('battery', h?.main_voltage != null ? `${h.main_voltage.toFixed(2)} В` : '—');
    text('charging', h?.backup_voltage != null ? `Резервная батарея: ${h.backup_voltage.toFixed(2)} В${s.healthFresh ? '' : ' · последний сигнал'}` : 'Напряжение ещё не поступало');
    diagnostics = h ? `START S-4011 · спутников: ${h.satellites ?? '—'}${s.healthFresh ? '' : ' · данные устарели'}` : 'Ожидаем диагностику START S-4011';
    if (s.healthFresh && !h.navigation_valid) diagnostics += '\nНет достоверной GPS-точки: проверьте обзор неба и установку';
  }
  text('battery-label', hardware ? 'Питание автомобиля' : 'Батарея трекера');
  $('battery-bar').parentElement.hidden = hardware;
  text('tracker-health', diagnostics);
}

function renderStats() {
  const s = report.summary;
  text('distance', `${s.distance_km.toLocaleString('ru-RU')} км`);
  text('moving', duration(s.moving_seconds)); text('parked', duration(s.stopped_seconds));
  text('max-speed', `${Math.round(s.max_speed_kmh)} км/ч`);
  text('first-last', `${fmtTime(s.first_point)} / ${fmtTime(s.last_point)}`);
  text('unknown', duration(s.unknown_seconds)); text('stop-count', s.stop_count);
  $('stops-list').replaceChildren();
  if (!report.stops.length) {
    const empty = document.createElement('div'); empty.className = 'no-stops';
    empty.textContent = s.point_count ? 'За этот день подтверждённых остановок от 5 минут нет.' : 'За выбранный день GPS-точек пока нет.';
    $('stops-list').append(empty);
  }
  report.stops.forEach((stop, i) => {
    const button = document.createElement('button'); button.className = 'stop-item';
    const number = document.createElement('span'); number.className = 'stop-number'; number.textContent = i + 1;
    const description = document.createElement('span'), title = document.createElement('strong'), detail = document.createElement('small');
    title.textContent = `${fmtTime(stop.start)}–${fmtTime(stop.end)} · ${duration(stop.duration_seconds)}`;
    detail.textContent = `${stop.latitude.toFixed(5)}, ${stop.longitude.toFixed(5)}${stop.ongoing ? ' · до последней точки' : ''}`;
    description.append(title, detail); button.append(number, description);
    button.addEventListener('click', () => {setMode('route'); map.setView([stop.latitude, stop.longitude], 16); $('map').scrollIntoView({behavior:'smooth', block:'center'});});
    $('stops-list').append(button);
  });
}

function renderMap() {
  if (!map || !report) return;
  layers.clearLayers(); if (car) {car.remove(); car = null;}
  if (mode === 'route') {
    report.segments.forEach(segment => L.polyline(segment.map(p => [p.latitude,p.longitude]), {color:'#ba2b28',weight:4,opacity:.85}).addTo(layers));
    report.stops.forEach((s, i) => {
      const marker = L.marker([s.latitude,s.longitude], {icon:L.divIcon({className:'stop-marker',html:String(i+1),iconSize:[26,26]})}).addTo(layers);
      const tooltip = document.createElement('span'); tooltip.textContent = `${fmtTime(s.start)}–${fmtTime(s.end)} · ${duration(s.duration_seconds)}`;
      marker.bindTooltip(tooltip);
    });
    text('map-note', report.summary.point_count ? `Маршрут · ${report.date} · ${report.summary.point_count} точек` : 'За выбранный день точек нет');
  } else if (latest?.point) {
    const p = latest.point;
    const artwork = document.createElement('img');
    artwork.src = '/car-safdecor.webp?v=13'; artwork.alt = 'Автомобиль SafDecor'; artwork.className = 'car-art';
    if (Number.isFinite(p.heading)) artwork.style.transform = `rotate(${p.heading}deg)`;
    car = L.marker([p.latitude,p.longitude], {title:'Автомобиль — последняя GPS-точка',
      icon:L.divIcon({className:'car-marker', html:artwork, iconSize:[44,44], iconAnchor:[22,22], tooltipAnchor:[0,-22]})}).addTo(map);
    sizeCarMarker();
    const label = document.createElement('span'); label.textContent = `${vehicles.find(v => String(v.id) === vehicleId())?.name || 'Автомобиль'} · ${fmtTime(p.gps_timestamp)}`;
    car.bindTooltip(label, {direction:'top',offset:[0,0]});
    if (Number.isFinite(p.accuracy)) L.circle([p.latitude,p.longitude], {radius:p.accuracy,color:'#ba2b28',weight:1,fillOpacity:.08}).addTo(layers);
    text('map-note', Number.isFinite(p.accuracy) ? `Последняя GPS-точка · точность ±${Math.round(p.accuracy)} м` : 'Последняя GPS-точка · прибор не передаёт точность в метрах');
  } else text('map-note', 'Ожидание первой точной GPS-точки');
  if (needFit) {fit(); needFit = false;}
  map.invalidateSize();
}

function fit() {
  if (!map) return;
  if (mode === 'live' && latest?.point) map.setView([latest.point.latitude, latest.point.longitude], 15);
  else if (layers.getBounds().isValid()) map.fitBounds(layers.getBounds(), {padding:[30,30],maxZoom:16});
}
function setMode(next) {mode=next; $('live-button').classList.toggle('active',next==='live'); $('route-button').classList.toggle('active',next==='route'); needFit=true; renderMap();}
function selectionChanged() {
  $('car-button').disabled = true; loadFavorite();
  generation++; latest=report=null; needFit=true; layers?.clearLayers(); if(car){car.remove();car=null;}
  for(const id of ['speed','battery','last-signal','last-contact','distance','moving','parked','max-speed','first-last','unknown']) text(id,'—');
  $('battery-bar').style.width='0%'; $('connection-status').className='status';text('connection-status','Обновление…');
  text('charging','Загрузка состояния');text('tracker-health','');text('map-note','Загрузка выбранного дня');text('stop-count','—');$('stops-list').replaceChildren();
  refresh();
}

async function loadDevices() {
  $('devices-list').replaceChildren();
  if (!vehicleId()) return;
  for (const d of await api(`/vehicles/${vehicleId()}/devices`)) {
    const row=document.createElement('div'); row.className='device-item';
    const label=document.createElement('span'); label.textContent=`${d.name} · ${d.kind === 'navtelecom' ? 'FLEX · ' : ''}${d.active?'активен':'отозван'}`;row.append(label);
    if(d.active){const button=document.createElement('button');button.textContent='Отозвать';button.className='quiet';
      button.addEventListener('click',async()=>{if(!confirm(`Отключить «${d.name}»? Сервер перестанет принимать его данные.`))return;
        try{await api(`/devices/${d.id}`,{method:'DELETE'});await loadDevices();}catch(e){text('manage-error',e.message);}});row.append(button);}
    $('devices-list').append(row);
  }
}
async function manage(){if(!canManage)return;text('manage-error','');$('token-result').hidden=true;$('device-token').value='';$('device-form').hidden=!vehicleId();$('manage-dialog').showModal();try{await loadDevices();}catch(e){text('manage-error',e.message);}}

$('login-form').addEventListener('submit',async e=>{e.preventDefault();const button=e.target.querySelector('button[type=submit]');button.disabled=true;text('login-error','');
  try{const data=Object.fromEntries(new FormData(e.target));data.remember_me=$('remember-me').checked;resetPassword();await enter(await api('/auth/login',{method:'POST',body:JSON.stringify(data)}));e.target.reset();}
  catch(error){text('login-error',error instanceof TypeError?'Сервер недоступен. Проверьте соединение.':error.message);if(csrf)warn(error.message);}finally{button.disabled=false;}});
$('logout-button').addEventListener('click',async()=>{try{await api('/auth/logout',{method:'POST'});showLogin();}catch(e){warn('Не удалось завершить сессию на сервере. Повторите выход после восстановления связи.');}});
$('manage-button').addEventListener('click',manage);$('add-first').addEventListener('click',manage);
$('close-manage').addEventListener('click',()=>$('manage-dialog').close());
$('manage-dialog').addEventListener('close',()=>{$('device-token').value='';$('token-result').hidden=true;});
$('vehicle-form').addEventListener('submit',async e=>{e.preventDefault();const button=e.target.querySelector('button');button.disabled=true;try{const v=await api('/vehicles',{method:'POST',body:JSON.stringify(Object.fromEntries(new FormData(e.target)))});await loadVehicles();$('vehicle-select').value=v.id;e.target.reset();$('device-form').hidden=false;$('hardware-form').hidden=false;selectionChanged();await loadDevices();}catch(err){text('manage-error',err.message);}finally{button.disabled=false;}});
$('device-form').addEventListener('submit',async e=>{e.preventDefault();const button=e.target.querySelector('button');button.disabled=true;try{const d=await api(`/vehicles/${vehicleId()}/devices`,{method:'POST',body:JSON.stringify(Object.fromEntries(new FormData(e.target)))});$('device-token').value=d.token;$('server-url').value=location.origin;$('token-result').hidden=false;e.target.reset();await loadDevices();}catch(err){text('manage-error',err.message);}finally{button.disabled=false;}});
$('hardware-form').addEventListener('submit', async e => {
  e.preventDefault(); const button = e.target.querySelector('button'); button.disabled = true;
  try {
    await api(`/vehicles/${vehicleId()}/hardware-devices`, {method:'POST', body:JSON.stringify(Object.fromEntries(new FormData(e.target)))});
    text('hardware-result', 'Трекер зарегистрирован. Теперь настройте соединение по инструкции INSTALL_NAVTELECOM. До первой связи телефон продолжит работать.');
    e.target.reset(); await loadDevices();
  } catch (err) {text('manage-error', err.message);} finally {button.disabled = false;}
});
$('vehicle-select').addEventListener('change',selectionChanged);
$('history-date').addEventListener('change',()=>{if(!$('history-date').value)return;setMode('route');selectionChanged();});
$('today-button').addEventListener('click',()=>{$('history-date').value=today();setMode('route');selectionChanged();});
$('live-button').addEventListener('click',()=>setMode('live'));$('route-button').addEventListener('click',()=>setMode('route'));$('fit-button').addEventListener('click',fit);
$('car-button').addEventListener('click', () => {if (!latest?.point) return; setMode('live'); map.setView([latest.point.latitude, latest.point.longitude], 16); car?.openTooltip();});
setInterval(()=>{if(!document.hidden)refresh();},15000);setInterval(renderLive,1000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
setupConvenience();
$('login-form').querySelector('button[type=submit]').disabled = false;
api('/auth/me').then(enter).catch(e=>{if(csrf)warn(e.message);});
