/* =========================================================================
   AI 진단 화면 동작
   입력 → (1) 브라우저에서 필수값 검사 → (2) fetch('/api/diagnose') 로 서버 호출
        → (3) 응답(JSON)을 화면에 표시  또는  (4) 실패 이유별 안내

   실패 처리 3종 (미션 요구사항)
   - 빈 입력: 제출 전에 막고 칸마다 빨간 안내 + "필수값을 입력하세요"
   - API 오류(4xx/5xx): 서버가 보낸 오류 코드별 안내 + 다시 시도 버튼
   - 지연/타임아웃: 10초 지나면 "오래 걸리고 있어요", 50초 지나면 요청 중단 후 안내
   화면에 넣는 글자는 모두 textContent 로 넣어 HTML 이 실행되지 않게 한다(XSS 방지).
   ========================================================================= */
(function () {
  'use strict';

  var API_URL = '/api/diagnose';
  var GOAL_MIN = 10;
  var GOAL_MAX = 500;
  var COOLDOWN_MS = 3000;   // 응답 뒤 3초 동안 재요청 막기 (AI 호출 비용·쿼터 보호)

  var DIMENSIONS = [
    { key: 'strategy', label: '전략·리더십' },
    { key: 'data', label: '데이터 기반' },
    { key: 'tech', label: '기술·인프라' },
    { key: 'people', label: '인재·조직문화' },
    { key: 'governance', label: '프로세스·거버넌스' }
  ];
  var INDUSTRY_LABELS = {
    semiconductor: '반도체·디스플레이', auto: '자동차·부품', battery: '이차전지·소재',
    machinery: '기계·장비', chemical: '화학·바이오', food: '식품·소비재', other: '기타 제조'
  };
  var SIZE_LABELS = {
    small: '소기업 (50명 미만)', medium: '중소기업 (50~299명)',
    midsize: '중견기업 (300~999명)', large: '대기업 (1,000명 이상)'
  };
  var SAMPLE = {
    company: '한빛정밀(가상)',
    industry: 'auto',
    size: 'medium',
    scores: { strategy: 3, data: 2, tech: 2, people: 3, governance: 2 },
    goal: '완성차에 납품하는 부품 회사입니다. 불량률을 줄이려고 비전검사에 AI를 도입하고 싶은데, 설비 데이터가 라인마다 따로 저장돼 있고 담당 인력도 부족합니다. 1년 안에 성과를 보여 줄 추진 순서가 궁금합니다.'
  };
  var LOADING_STEPS = [
    { after: 0, text: '입력 내용을 확인하고 있어요' },
    { after: 1500, text: 'AI가 5개 영역을 분석하고 있어요' },
    { after: 6000, text: '로드맵과 KPI를 정리하고 있어요' }
  ];

  var form = document.getElementById('diagnose-form');
  if (!form) return;

  var $ = function (id) { return document.getElementById(id); };
  var els = {
    company: $('company'), industry: $('industry'), size: $('size'), goal: $('goal'),
    goalCount: $('goal-count'), formAlert: $('form-alert'), submit: $('submit-btn'),
    fillSample: $('fill-sample'), reset: $('reset-form'),
    loading: $('loading'), loadingStep: $('loading-step'), loadingElapsed: $('loading-elapsed'), loadingSlow: $('loading-slow'),
    error: $('request-error'), errorTitle: $('request-error-title'), errorMessage: $('request-error-message'),
    errorCode: $('request-error-code'), retry: $('retry-btn'),
    result: $('result'), resultHeading: $('result-heading'), resultLevel: $('result-level'),
    resultTotal: $('result-total'), resultLevelDesc: $('result-level-desc'), resultChart: $('result-chart'),
    resultScores: $('result-scores'), resultSummary: $('result-summary'), resultStrengths: $('result-strengths'),
    resultGaps: $('result-gaps'), resultRoadmap: $('result-roadmap'), resultKpis: $('result-kpis'),
    resultQuickwin: $('result-quickwin'), resultCaution: $('result-caution'), resultMeta: $('result-meta'),
    copy: $('copy-btn'), print: $('print-btn'), again: $('again-btn'), toast: $('toast')
  };

  function toNumber(value, fallback) {
    var number = Number(value);
    return isFinite(number) && number > 0 ? number : fallback;
  }
  var TIMEOUT_MS = toNumber(form.dataset.timeoutMs, 50000);
  var SLOW_MS = toNumber(form.dataset.slowMs, 10000);

  var state = { busy: false, cooldownUntil: 0, lastPayload: null, lastResult: null, lastMeta: null };

  /* ---------------------------------------------------------------------
     1. 입력 모으기와 검사
     --------------------------------------------------------------------- */
  function collectPayload() {
    var scores = {};
    DIMENSIONS.forEach(function (dim) {
      var checked = form.querySelector('input[name="score-' + dim.key + '"]:checked');
      scores[dim.key] = checked ? Number(checked.value) : null;
    });
    return {
      company: els.company.value.trim(),
      industry: els.industry.value,
      size: els.size.value,
      scores: scores,
      goal: els.goal.value.trim()
    };
  }

  function validatePayload(payload) {
    var errors = [];
    if (!payload.industry) errors.push({ field: 'industry', message: '업종을 선택해 주세요.', empty: true });
    if (!payload.size) errors.push({ field: 'size', message: '기업 규모를 선택해 주세요.', empty: true });
    DIMENSIONS.forEach(function (dim) {
      if (!payload.scores[dim.key]) {
        errors.push({ field: 'scores.' + dim.key, message: "'" + dim.label + "' 점수를 선택해 주세요.", empty: true });
      }
    });
    var length = payload.goal.length;
    if (!length) errors.push({ field: 'goal', message: '고민이나 목표를 적어 주세요.', empty: true });
    else if (length < GOAL_MIN) errors.push({ field: 'goal', message: GOAL_MIN + '자 이상 적어 주세요. (지금 ' + length + '자)' });
    else if (length > GOAL_MAX) errors.push({ field: 'goal', message: GOAL_MAX + '자 이내로 줄여 주세요. (지금 ' + length + '자)' });
    return errors;
  }

  function fieldNodes(field) {
    if (field.indexOf('scores.') === 0) {
      var key = field.split('.')[1];
      return { box: $('group-' + key), error: $('error-scores-' + key), focus: form.querySelector('input[name="score-' + key + '"]'), label: labelOf(key) + ' 점수' };
    }
    var names = { industry: '업종', size: '기업 규모', goal: '고민·목표', scores: '영역별 점수' };
    return { box: $('field-' + field), error: $('error-' + field), focus: els[field], label: names[field] || field };
  }

  function labelOf(key) {
    for (var i = 0; i < DIMENSIONS.length; i++) if (DIMENSIONS[i].key === key) return DIMENSIONS[i].label;
    return key;
  }

  function clearErrors() {
    form.querySelectorAll('.has-error').forEach(function (node) { node.classList.remove('has-error'); });
    form.querySelectorAll('.field-error').forEach(function (node) { node.textContent = ''; });
    form.querySelectorAll('[aria-invalid]').forEach(function (node) { node.removeAttribute('aria-invalid'); });
    els.formAlert.hidden = true;
    els.formAlert.textContent = '';
  }

  function showFieldErrors(errors) {
    clearErrors();
    var missing = [];
    errors.forEach(function (error) {
      var nodes = fieldNodes(error.field);
      if (nodes.box) nodes.box.classList.add('has-error');
      if (nodes.error) nodes.error.textContent = error.message;
      if (nodes.focus && nodes.focus.tagName !== 'INPUT') nodes.focus.setAttribute('aria-invalid', 'true');
      if (error.empty) missing.push(nodes.label);
    });
    els.formAlert.textContent = missing.length
      ? '필수값을 입력하세요: ' + missing.join(', ')
      : '입력값을 확인해 주세요: ' + errors[0].message;
    els.formAlert.hidden = false;
    var first = fieldNodes(errors[0].field).focus;
    if (first) first.focus({ preventScroll: true });
    els.formAlert.scrollIntoView({ behavior: smoothOrAuto(), block: 'center' });
  }

  function updateCounter() {
    var length = els.goal.value.trim().length;
    var short = length > 0 && length < GOAL_MIN;
    els.goalCount.textContent = length + ' / ' + GOAL_MAX + '자' + (short ? ' (' + GOAL_MIN + '자 이상)' : '');
    els.goalCount.classList.toggle('is-short', short);
  }

  /* ---------------------------------------------------------------------
     2. 요청 보내기 (fetch) 와 상태 표시
     --------------------------------------------------------------------- */
  var timers = { interval: null, slow: null, timeout: null, cooldown: null };

  function startLoading() {
    var started = Date.now();
    els.loading.hidden = false;
    els.loadingSlow.hidden = true;
    els.loadingStep.textContent = LOADING_STEPS[0].text;
    els.loadingElapsed.textContent = '0';
    timers.interval = setInterval(function () {
      var passed = Date.now() - started;
      els.loadingElapsed.textContent = String(Math.floor(passed / 1000));
      for (var i = LOADING_STEPS.length - 1; i >= 0; i--) {
        if (passed >= LOADING_STEPS[i].after) { els.loadingStep.textContent = LOADING_STEPS[i].text; break; }
      }
    }, 250);
    timers.slow = setTimeout(function () { els.loadingSlow.hidden = false; }, SLOW_MS);   // 지연 안내
  }

  function stopLoading() {
    clearInterval(timers.interval);
    clearTimeout(timers.slow);
    els.loading.hidden = true;
  }

  function setBusy(busy) {
    state.busy = busy;
    form.setAttribute('aria-busy', String(busy));
    els.submit.disabled = busy;
    els.submit.textContent = busy ? '분석 중…' : 'AI 진단 받기';
  }

  function startCooldown() {
    state.cooldownUntil = Date.now() + COOLDOWN_MS;
    els.submit.disabled = true;
    var tick = function () {
      var left = Math.ceil((state.cooldownUntil - Date.now()) / 1000);
      if (left <= 0) {
        clearInterval(timers.cooldown);
        els.submit.disabled = false;
        els.submit.textContent = 'AI 진단 받기';
        return;
      }
      els.submit.textContent = left + '초 후 다시 요청할 수 있어요';
    };
    clearInterval(timers.cooldown);
    tick();
    timers.cooldown = setInterval(tick, 250);
  }

  function readJson(response) {
    return response.text().then(function (text) {
      if (!text) return null;
      try { return JSON.parse(text); } catch (e) { return null; }   // Vercel 기본 오류 페이지(HTML)일 수 있음
    });
  }

  async function submitDiagnosis(event) {
    if (event) event.preventDefault();
    if (state.busy) return;
    if (Date.now() < state.cooldownUntil) { showToast('잠시 후 다시 요청할 수 있어요'); return; }

    var payload = collectPayload();
    var errors = validatePayload(payload);
    if (errors.length) { showFieldErrors(errors); return; }   // (1) 빈 입력: 서버를 부르지 않는다

    clearErrors();
    hideRequestError();
    els.result.hidden = true;
    setBusy(true);
    startLoading();

    var controller = typeof AbortController === 'function' ? new AbortController() : null;
    var timedOut = false;
    timers.timeout = setTimeout(function () {                // (3) 타임아웃: 50초 뒤 요청 중단
      timedOut = true;
      if (controller) controller.abort();
    }, TIMEOUT_MS);

    try {
      var response = await fetch(API_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal: controller ? controller.signal : undefined
      });
      var data = await readJson(response);
      if (timedOut) throw { kind: 'timeout' };
      if (!response.ok || !data || data.ok !== true) {        // (2) API 오류: 4xx / 5xx
        throw { kind: 'http', status: response.status, data: data };
      }
      state.lastPayload = payload;
      renderResult(data.result, data.meta || {}, payload);
    } catch (error) {
      if (timedOut) error = { kind: 'timeout' };
      showRequestError(describeFailure(error));
    } finally {
      clearTimeout(timers.timeout);
      stopLoading();
      setBusy(false);
      startCooldown();
    }
  }

  /* ---------------------------------------------------------------------
     3. 실패 안내
     --------------------------------------------------------------------- */
  var TITLES = {
    EMPTY_INPUT: '필수값을 입력하세요', INVALID_INPUT: '입력값을 확인해 주세요', TOO_LONG: '입력이 너무 길어요',
    BAD_JSON: '요청 형식 오류', BAD_REQUEST: '요청 형식 오류', TOO_LARGE: '입력이 너무 커요',
    RATE_LIMITED: '요청이 많아요', CONFIG_MISSING_KEY: '서버 설정이 필요해요', CONFIG_INVALID: '서버 설정이 필요해요',
    AI_AUTH_ERROR: 'AI 서비스 인증 오류', AI_MODEL_NOT_FOUND: 'AI 모델 설정 오류', AI_BAD_REQUEST: 'AI 요청 거절',
    AI_UPSTREAM_ERROR: 'AI 서버 오류', AI_UNREACHABLE: 'AI 서버 연결 실패', AI_BLOCKED: 'AI가 답하지 않았어요',
    AI_BAD_OUTPUT: 'AI 응답 형식 오류', AI_TIMEOUT: '응답 시간 초과', SERVER_ERROR: '서버 오류',
    METHOD_NOT_ALLOWED: '요청 방식 오류'
  };

  function describeFailure(error) {
    if (error && error.kind === 'timeout') {
      return {
        title: '응답 시간 초과',
        message: '응답이 ' + Math.round(TIMEOUT_MS / 1000) + '초 넘게 오지 않아 요청을 멈췄어요. 잠시 후 다시 시도해 주세요.',
        code: 'CLIENT_TIMEOUT'
      };
    }
    if (error && error.kind === 'http') {
      var serverError = error.data && error.data.error;
      if (serverError && serverError.code) {
        if (error.status === 400 && serverError.field) showFieldErrors([{ field: serverError.field, message: serverError.message, empty: serverError.code === 'EMPTY_INPUT' }]);
        return {
          title: TITLES[serverError.code] || '요청을 처리하지 못했어요',
          message: serverError.message,
          code: serverError.code + ' · HTTP ' + error.status
        };
      }
      return fallbackByStatus(error.status);                  // JSON 이 아닌 오류(예: Vercel 기본 504 페이지)
    }
    return {                                                 // fetch 자체가 실패: 인터넷 끊김, 서버 꺼짐 등
      title: '서버에 연결하지 못했어요',
      message: '인터넷 연결을 확인하고 다시 시도해 주세요.',
      code: 'NETWORK_ERROR'
    };
  }

  function fallbackByStatus(status) {
    if (status === 404) return { title: 'API를 찾을 수 없어요', message: 'API 주소(/api/diagnose)를 찾지 못했어요. 배포 설정을 확인해 주세요.', code: 'HTTP 404' };
    if (status === 429) return { title: '요청이 많아요', message: '잠시 후 다시 시도해 주세요.', code: 'HTTP 429' };
    if (status === 504) return { title: '응답 시간 초과', message: '서버 응답 시간이 초과됐어요. 잠시 후 다시 시도해 주세요.', code: 'HTTP 504' };
    if (status >= 500) return { title: '서버 오류', message: '서버 오류가 발생했어요. 잠시 후 다시 시도해 주세요.', code: 'HTTP ' + status };
    return { title: '요청을 처리하지 못했어요', message: '잠시 후 다시 시도해 주세요.', code: 'HTTP ' + status };
  }

  function showRequestError(info) {
    els.errorTitle.textContent = info.title;
    els.errorMessage.textContent = info.message;
    els.errorCode.textContent = '오류 코드: ' + info.code;
    els.error.hidden = false;
    els.error.scrollIntoView({ behavior: smoothOrAuto(), block: 'center' });
  }

  function hideRequestError() { els.error.hidden = true; }

  /* ---------------------------------------------------------------------
     4. 결과 그리기 (모든 글자는 textContent 로)
     --------------------------------------------------------------------- */
  function fillList(list, items) {
    list.textContent = '';
    (items || []).forEach(function (item) {
      var li = document.createElement('li');
      li.textContent = item;
      list.appendChild(li);
    });
  }

  function add(parent, tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    parent.appendChild(node);
    return node;
  }

  function renderResult(result, meta, payload) {
    state.lastResult = result;
    state.lastMeta = meta;

    els.resultHeading.textContent = (payload.company ? payload.company + ' ' : '') + 'AX 진단 결과';
    els.resultLevel.textContent = result.level + '단계 · ' + result.level_name;
    els.resultTotal.textContent = '합계 ' + result.total + '점 · 평균 ' + Number(result.average).toFixed(1);
    els.resultLevelDesc.textContent = result.level_desc || '';

    var items = DIMENSIONS.map(function (dim) { return { label: dim.label, value: result.scores[dim.key] }; });
    if (window.AXRadar) window.AXRadar.render(els.resultChart, items, { animate: true, title: '우리 회사 영역별 점수' });

    var weakest = result.weakest || [];
    els.resultScores.textContent = '';
    DIMENSIONS.forEach(function (dim) {
      var value = result.scores[dim.key];
      var row = add(els.resultScores, 'tr');
      add(row, 'td', 'name', dim.label);
      var bar = add(add(row, 'td', 'bar-cell'), 'span', 'bar');
      bar.setAttribute('aria-hidden', 'true');
      add(bar, 'i').style.width = (value / 5 * 100) + '%';
      add(row, 'td', 'value', value + '점');
      var flag = add(row, 'td', 'flag');
      if (weakest.indexOf(dim.key) !== -1) add(flag, 'span', '', '보완');
    });

    els.resultSummary.textContent = result.summary;
    fillList(els.resultStrengths, result.strengths);
    fillList(els.resultGaps, result.gaps);

    els.resultRoadmap.textContent = '';
    (result.roadmap || []).forEach(function (step) {
      var li = add(els.resultRoadmap, 'li');
      add(li, 'p', 'phase', step.phase);
      add(li, 'p', 'phase-title', step.title);
      fillList(add(li, 'ul'), step.actions);
    });

    els.resultKpis.textContent = '';
    (result.kpis || []).forEach(function (kpi) {
      var tr = add(els.resultKpis, 'tr');
      add(tr, 'td', '', kpi.name);
      add(tr, 'td', '', kpi.target).setAttribute('data-label', '목표');
      add(tr, 'td', '', kpi.why).setAttribute('data-label', '이유');
    });

    els.resultQuickwin.textContent = result.quick_win || '결과에 포함되지 않았어요.';
    els.resultCaution.textContent = result.caution || '결과에 포함되지 않았어요.';

    els.resultMeta.textContent = '';
    if (meta.provider === 'mock') add(els.resultMeta, 'span', 'mock', '로컬 목업 응답(실제 AI 아님) · ');
    var seconds = meta.elapsed_ms ? (meta.elapsed_ms / 1000).toFixed(1) + '초' : '';
    add(els.resultMeta, 'span', '', ['분석 엔진: ' + (meta.provider || '-'), meta.model, seconds].filter(Boolean).join(' · ')
      + ' | AI가 만든 초안이라 사실 확인이 필요해요.');

    els.result.hidden = false;
    els.result.scrollIntoView({ behavior: smoothOrAuto(), block: 'start' });
    els.resultHeading.focus({ preventScroll: true });
  }

  /* ---------------------------------------------------------------------
     5. 복사·인쇄·예시·초기화·토스트
     --------------------------------------------------------------------- */
  function buildPlainText() {
    var r = state.lastResult, p = state.lastPayload || {};
    if (!r) return '';
    var lines = [
      '[AX 레이더 진단 결과]',
      '회사: ' + (p.company || '(입력 안 함)') + ' | 업종: ' + (INDUSTRY_LABELS[p.industry] || '') + ' | 규모: ' + (SIZE_LABELS[p.size] || ''),
      '단계: ' + r.level + '단계 ' + r.level_name + ' (합계 ' + r.total + '점, 평균 ' + Number(r.average).toFixed(1) + ')',
      '영역 점수: ' + DIMENSIONS.map(function (d) { return d.label + ' ' + r.scores[d.key]; }).join(' / '),
      '',
      '요약: ' + r.summary,
      '강점:'
    ];
    (r.strengths || []).forEach(function (s) { lines.push(' - ' + s); });
    lines.push('보완점:');
    (r.gaps || []).forEach(function (s) { lines.push(' - ' + s); });
    lines.push('', '12개월 로드맵:');
    (r.roadmap || []).forEach(function (step) {
      lines.push(' [' + step.phase + '] ' + step.title);
      (step.actions || []).forEach(function (a) { lines.push('   - ' + a); });
    });
    lines.push('', '추천 KPI:');
    (r.kpis || []).forEach(function (k) { lines.push(' - ' + k.name + ': ' + k.target + ' (' + k.why + ')'); });
    lines.push('', '이번 주 바로 할 일: ' + (r.quick_win || '-'), '주의할 점: ' + (r.caution || '-'), '', '※ AI가 만든 초안이므로 사실 확인이 필요합니다.');
    return lines.join('\n');
  }

  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(text);
    return new Promise(function (resolve, reject) {          // 예전 브라우저용 대체 방법
      var area = document.createElement('textarea');
      area.value = text;
      area.setAttribute('readonly', '');
      area.style.position = 'fixed';
      area.style.opacity = '0';
      document.body.appendChild(area);
      area.select();
      try { document.execCommand('copy') ? resolve() : reject(new Error('copy failed')); } catch (e) { reject(e); }
      document.body.removeChild(area);
    });
  }

  var toastTimer = null;
  function showToast(message) {
    els.toast.textContent = message;
    els.toast.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { els.toast.hidden = true; }, 2200);
  }

  function smoothOrAuto() {
    return window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth';
  }

  function fillSample() {
    els.company.value = SAMPLE.company;
    els.industry.value = SAMPLE.industry;
    els.size.value = SAMPLE.size;
    DIMENSIONS.forEach(function (dim) {
      var radio = $('score-' + dim.key + '-' + SAMPLE.scores[dim.key]);
      if (radio) radio.checked = true;
    });
    els.goal.value = SAMPLE.goal;
    updateCounter();
    clearErrors();
    showToast('예시 값을 채웠어요. AI 진단 받기를 눌러 보세요.');
  }

  function resetForm() {
    form.reset();
    updateCounter();
    clearErrors();
    hideRequestError();
    els.result.hidden = true;
    showToast('입력을 모두 지웠어요.');
  }

  /* ---------------------------------------------------------------------
     6. 이벤트 연결
     --------------------------------------------------------------------- */
  form.addEventListener('submit', submitDiagnosis);
  els.goal.addEventListener('input', updateCounter);
  els.fillSample.addEventListener('click', fillSample);
  els.reset.addEventListener('click', resetForm);
  els.retry.addEventListener('click', function () { submitDiagnosis(); });
  els.copy.addEventListener('click', function () {
    copyText(buildPlainText()).then(function () { showToast('결과를 복사했어요.'); }, function () { showToast('복사하지 못했어요. 직접 선택해 복사해 주세요.'); });
  });
  els.print.addEventListener('click', function () { window.print(); });
  els.again.addEventListener('click', function () {
    $('diagnose').scrollIntoView({ behavior: smoothOrAuto(), block: 'start' });
    els.industry.focus({ preventScroll: true });
  });

  // 입력을 고치면 그 칸의 오류 표시를 바로 지운다
  form.addEventListener('change', function (event) {
    var target = event.target;
    var box = target.closest('.score-group, .field');
    if (box && box.classList.contains('has-error')) {
      box.classList.remove('has-error');
      var error = box.querySelector('.field-error');
      if (error) error.textContent = '';
      target.removeAttribute('aria-invalid');
    }
  });

  updateCounter();
})();
