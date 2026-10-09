'use strict';

function resetPassword() {
  $('login-password').type = 'password';
  $('password-toggle').setAttribute('aria-label', 'Показать пароль');
  $('password-toggle').setAttribute('aria-pressed', 'false');
  $('eye-slash').setAttribute('hidden', '');
  $('caps-warning').hidden = true;
}

function favoriteKey() {return `gps-favorite-v1:${encodeURIComponent(sessionUser)}:${vehicleId()}`;}
function clearFavorite() {
  favoriteMarker?.remove(); favoriteMarker = null; favorite = null;
  pickingStop = false; pendingStop = null;
  $('map').classList.remove('picking-stop'); $('favorite-form').hidden = true;
}
function loadFavorite() {
  clearFavorite();
  try {
    const saved = JSON.parse(localStorage.getItem(favoriteKey()));
    if (saved && typeof saved.name === 'string' && saved.name.length <= 80 &&
        Number.isFinite(saved.lat) && Math.abs(saved.lat) <= 90 &&
        Number.isFinite(saved.lng) && Math.abs(saved.lng) <= 180) favorite = saved;
  } catch { /* Storage can be disabled; the rest of the map remains available. */ }
  renderFavorite();
}
function renderFavorite() {
  favoriteMarker?.remove(); favoriteMarker = null;
  text('favorite-name', favorite?.name || 'Выберите место посадки');
  text('favorite-note', favorite ? 'Ваша отметка на карте. Время прибытия пока не рассчитывается.' : 'Отметьте точку на карте. Выбор сохранится в этом браузере.');
  text('favorite-pick', favorite ? 'Изменить' : 'Выбрать на карте');
  $('favorite-pick').hidden = false;
  $('favorite-show').hidden = $('favorite-remove').hidden = !favorite;
  if (map && favorite) drawFavorite(favorite);
}
function drawFavorite(point) {
  favoriteMarker?.remove();
  const label = document.createElement('span'); label.textContent = point.name || 'Моя остановка';
  favoriteMarker = L.marker([point.lat, point.lng], {
    title: label.textContent, icon: L.divIcon({className:'favorite-marker', html:'★', iconSize:[30,30]})
  }).addTo(map).bindTooltip(label);
}
function chooseStopPoint(event) {
  if (!pickingStop || !csrf) return;
  pendingStop = {lat: event.latlng.lat, lng: event.latlng.lng};
  drawFavorite(pendingStop);
  text('favorite-note', 'Точка выбрана. Введите название и сохраните; её можно передвинуть другим нажатием на карту.');
  $('favorite-form').scrollIntoView({behavior:'smooth', block:'nearest'});
  $('favorite-input').focus({preventScroll:true});
}
function setupConvenience() {
  $('password-toggle').addEventListener('click', () => {
    const shown = $('login-password').type === 'password';
    $('login-password').type = shown ? 'text' : 'password';
    $('password-toggle').setAttribute('aria-label', shown ? 'Скрыть пароль' : 'Показать пароль');
    $('password-toggle').setAttribute('aria-pressed', String(shown));
    $('eye-slash').toggleAttribute('hidden', !shown);
  });
  for (const event of ['keydown', 'keyup']) $('login-password').addEventListener(event, e => {
    $('caps-warning').hidden = !e.getModifierState?.('CapsLock');
  });
  $('login-password').addEventListener('blur', () => {$('caps-warning').hidden = true;});
  document.addEventListener('visibilitychange', () => {if (document.hidden) resetPassword();});
  $('favorite-pick').addEventListener('click', () => {
    if (!map) return;
    pickingStop = true; pendingStop = null; needFit = false;
    $('map').classList.add('picking-stop'); $('favorite-form').hidden = false;
    $('favorite-pick').hidden = true; $('favorite-input').value = favorite?.name || '';
    text('favorite-note', 'Нажмите на карту в месте посадки, затем сохраните название.');
    $('map').scrollIntoView({behavior:'smooth', block:'center'});
  });
  $('favorite-cancel').addEventListener('click', () => {loadFavorite();});
  $('favorite-form').addEventListener('submit', e => {
    e.preventDefault(); const name = $('favorite-input').value.trim();
    if (!pendingStop || !name) {text('favorite-note', 'Укажите точку на карте и название остановки.'); return;}
    const value = {...pendingStop, name};
    try {localStorage.setItem(favoriteKey(), JSON.stringify(value));}
    catch {text('favorite-note', 'Браузер запретил сохранение. Разрешите хранение данных сайта и повторите.'); return;}
    loadFavorite(); favoriteMarker?.openTooltip();
  });
  $('favorite-remove').addEventListener('click', () => {
    try {localStorage.removeItem(favoriteKey()); loadFavorite();}
    catch {text('favorite-note', 'Не удалось убрать отметку: браузер запретил доступ к хранилищу.');}
  });
  $('favorite-show').addEventListener('click', () => {
    if (!favorite || !map) return;
    needFit = false; map.setView([favorite.lat, favorite.lng], 16); favoriteMarker?.openTooltip();
    $('map').scrollIntoView({behavior:'smooth', block:'center'});
  });
  let installPrompt = null;
  const standalone = matchMedia('(display-mode: standalone)');
  function installed() {return standalone.matches || navigator.standalone === true;}
  $('install-button').hidden = installed();
  standalone.addEventListener('change', () => {$('install-button').hidden = installed();});
  window.addEventListener('beforeinstallprompt', event => {event.preventDefault(); installPrompt = event;});
  window.addEventListener('appinstalled', () => {installPrompt = null; $('install-button').hidden = true; $('install-dialog').close();});
  $('install-button').addEventListener('click', async () => {
    if (installPrompt) {
      const prompt = installPrompt; installPrompt = null;
      try {await prompt.prompt(); await prompt.userChoice;} catch {$('install-dialog').showModal();}
    } else $('install-dialog').showModal();
  });
  $('close-install').addEventListener('click', () => {$('install-dialog').close();});
}
