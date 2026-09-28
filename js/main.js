/* =========================================================================
   공통 화면 동작
   1) 다크 모드 전환(선택 기억)  2) 모바일 메뉴 열기/닫기
   3) 지금 보는 섹션의 메뉴 강조  4) 홈 화면 예시 레이더 차트
   ========================================================================= */
(function () {
  'use strict';

  var root = document.documentElement;

  /* 1) 다크 모드 ------------------------------------------------------- */
  var themeButton = document.getElementById('theme-toggle');
  var darkQuery = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;

  function currentTheme() {
    var chosen = root.getAttribute('data-theme');
    if (chosen === 'dark' || chosen === 'light') return chosen;
    return darkQuery && darkQuery.matches ? 'dark' : 'light';
  }

  function syncThemeButton() {
    if (!themeButton) return;
    var isDark = currentTheme() === 'dark';
    themeButton.setAttribute('aria-label', isDark ? '라이트 모드로 전환' : '다크 모드로 전환');
    themeButton.setAttribute('aria-pressed', String(isDark));
  }

  if (themeButton) {
    themeButton.addEventListener('click', function () {
      var next = currentTheme() === 'dark' ? 'light' : 'dark';
      root.setAttribute('data-theme', next);
      try { window.localStorage.setItem('ax-theme', next); } catch (e) { /* 저장 못 해도 이번 방문에는 적용 */ }
      syncThemeButton();
    });
    if (darkQuery && darkQuery.addEventListener) darkQuery.addEventListener('change', syncThemeButton);
    syncThemeButton();
  }

  /* 2) 모바일 메뉴 ------------------------------------------------------ */
  var menuButton = document.getElementById('menu-toggle');
  var nav = document.getElementById('site-nav');

  function setMenu(open) {
    if (!nav || !menuButton) return;
    nav.classList.toggle('is-open', open);
    menuButton.setAttribute('aria-expanded', String(open));
    menuButton.setAttribute('aria-label', open ? '메뉴 닫기' : '메뉴 열기');
  }

  if (nav && menuButton) {
    menuButton.addEventListener('click', function () {
      setMenu(!nav.classList.contains('is-open'));
    });
    nav.addEventListener('click', function (event) {
      if (event.target.closest('a')) setMenu(false);           // 메뉴를 고르면 닫기
    });
    document.addEventListener('click', function (event) {
      var outside = !nav.contains(event.target) && !menuButton.contains(event.target);
      if (nav.classList.contains('is-open') && outside) setMenu(false);   // 바깥을 누르면 닫기
    });
    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape' && nav.classList.contains('is-open')) {
        setMenu(false);
        menuButton.focus();
      }
    });
    window.addEventListener('resize', function () {
      if (window.innerWidth > 860) setMenu(false);
    });
  }

  /* 3) 현재 위치 메뉴 강조 -------------------------------------------- */
  var links = Array.prototype.slice.call(document.querySelectorAll('[data-nav]'));
  var sections = links
    .map(function (link) { return document.querySelector(link.getAttribute('href')); })
    .filter(Boolean);

  function setActive(id) {
    links.forEach(function (link) {
      if (link.getAttribute('href') === '#' + id) link.setAttribute('aria-current', 'true');
      else link.removeAttribute('aria-current');
    });
  }

  if ('IntersectionObserver' in window && sections.length) {
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) setActive(entry.target.id);
      });
    }, { rootMargin: '-45% 0px -50% 0px' });
    sections.forEach(function (section) { observer.observe(section); });

    // 맨 아래까지 내리면 마지막 섹션(소개)을 강조
    window.addEventListener('scroll', function () {
      var atBottom = window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 4;
      if (atBottom) setActive(sections[sections.length - 1].id);
    }, { passive: true });
  }

  /* 4) 홈 화면 예시 차트 ------------------------------------------------ */
  var heroRadar = document.getElementById('hero-radar');
  if (heroRadar && window.AXRadar) {
    window.AXRadar.render(heroRadar, [
      { label: '전략·리더십', value: 3 },
      { label: '데이터 기반', value: 2 },
      { label: '기술·인프라', value: 2 },
      { label: '인재·조직문화', value: 3 },
      { label: '프로세스·거버넌스', value: 2 }
    ], { sweep: true, title: '예시 레이더 차트' });
  }

  /* 푸터 연도 */
  var year = document.getElementById('year');
  if (year) year.textContent = String(new Date().getFullYear());
})();
