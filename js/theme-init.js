/* 페이지를 그리기 전에 저장된 테마(라이트/다크)를 먼저 적용해 깜빡임을 막는다. */
(function () {
  try {
    var saved = window.localStorage.getItem('ax-theme');
    if (saved === 'dark' || saved === 'light') {
      document.documentElement.setAttribute('data-theme', saved);
    }
  } catch (e) {
    /* 저장소를 쓸 수 없는 브라우저(사생활 보호 모드 등)는 시스템 설정을 따른다 */
  }
})();
