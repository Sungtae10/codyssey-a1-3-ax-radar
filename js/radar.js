/* =========================================================================
   레이더 차트 그리기 (SVG, 외부 라이브러리 없음)
   사용법: AXRadar.render(담을 요소, [{label: '전략·리더십', value: 3}, ...], {max: 5})
   - 5개 축을 12시 방향부터 시계 방향으로 배치
   - 1~5 눈금 오각형, 점수 영역, 점(마우스를 올리면 점수 표시), 축 이름과 점수
   ========================================================================= */
(function (global) {
  'use strict';

  var NS = 'http://www.w3.org/2000/svg';
  var VIEW_W = 400;
  var VIEW_H = 360;
  var CX = 200;
  var CY = 182;
  var RADIUS = 104;

  function make(name, attrs, parent) {
    var node = document.createElementNS(NS, name);
    Object.keys(attrs || {}).forEach(function (key) {
      node.setAttribute(key, attrs[key]);
    });
    if (parent) parent.appendChild(node);
    return node;
  }

  function pointAt(index, count, ratio) {
    var angle = (-90 + (360 / count) * index) * Math.PI / 180;
    return {
      x: CX + RADIUS * ratio * Math.cos(angle),
      y: CY + RADIUS * ratio * Math.sin(angle),
      cos: Math.cos(angle),
      sin: Math.sin(angle)
    };
  }

  function toPoints(list) {
    return list.map(function (p) { return p.x.toFixed(1) + ',' + p.y.toFixed(1); }).join(' ');
  }

  /* 긴 이름("프로세스·거버넌스")은 가운뎃점 뒤에서 두 줄로 나눠 차트 밖으로 넘치지 않게 한다. */
  function splitLabel(label) {
    if (label.length <= 7 || label.indexOf('·') === -1) return [label];
    var cut = label.indexOf('·') + 1;
    return [label.slice(0, cut), label.slice(cut)];
  }

  function reducedMotion() {
    return global.matchMedia && global.matchMedia('(prefers-reduced-motion: reduce)').matches;
  }

  function render(container, items, options) {
    if (!container || !items || !items.length) return;
    options = options || {};
    var max = options.max || 5;
    var count = items.length;

    container.textContent = '';
    var svg = make('svg', { viewBox: '0 0 ' + VIEW_W + ' ' + VIEW_H, 'aria-hidden': 'true', focusable: 'false' }, container);

    // 1) 눈금 오각형과 축
    for (var level = 1; level <= max; level++) {
      var ring = [];
      for (var i = 0; i < count; i++) ring.push(pointAt(i, count, level / max));
      make('polygon', { points: toPoints(ring), class: 'radar-grid' }, svg);
    }
    for (var a = 0; a < count; a++) {
      var end = pointAt(a, count, 1);
      make('line', { x1: CX, y1: CY, x2: end.x.toFixed(1), y2: end.y.toFixed(1), class: 'radar-axis' }, svg);
    }
    for (var t = 1; t <= max; t++) {
      var tick = make('text', { x: CX + 8, y: (CY - RADIUS * t / max + 4).toFixed(1), class: 'radar-tick' }, svg);
      tick.textContent = String(t);
    }

    // 2) (홈 화면 전용) 레이더처럼 돌아가는 빛줄기
    if (options.sweep && !reducedMotion()) {
      var edge = pointAt(1, 10, 1);
      var sweep = make('path', {
        d: 'M' + CX + ' ' + CY + ' L' + CX + ' ' + (CY - RADIUS) + ' A' + RADIUS + ' ' + RADIUS + ' 0 0 1 ' + edge.x.toFixed(1) + ' ' + edge.y.toFixed(1) + ' Z',
        class: 'radar-sweep'
      }, svg);
      make('animateTransform', {
        attributeName: 'transform', type: 'rotate', from: '0 ' + CX + ' ' + CY, to: '360 ' + CX + ' ' + CY,
        dur: '6s', repeatCount: 'indefinite'
      }, sweep);
    }

    // 3) 점수 영역
    var points = items.map(function (item, index) {
      var value = Math.max(0, Math.min(max, Number(item.value) || 0));
      return pointAt(index, count, value / max);
    });
    make('polygon', { points: toPoints(points), class: 'radar-area' + (options.animate ? ' is-animated' : '') }, svg);

    // 4) 점 + 마우스를 올리면 보이는 설명(title)
    points.forEach(function (p, index) {
      var dot = make('circle', { cx: p.x.toFixed(1), cy: p.y.toFixed(1), r: 5, class: 'radar-point' }, svg);
      var title = make('title', {}, dot);
      title.textContent = items[index].label + ': ' + items[index].value + '점';
    });

    // 5) 축 이름과 점수
    items.forEach(function (item, index) {
      var anchor = pointAt(index, count, 1);
      var lx = CX + (RADIUS + 18) * anchor.cos;
      var ly = CY + (RADIUS + 18) * anchor.sin;
      var textAnchor = anchor.cos > 0.3 ? 'start' : (anchor.cos < -0.3 ? 'end' : 'middle');
      var lines = splitLabel(item.label);
      lines.push(item.value + '점');
      var lineHeight = 16;
      var startY;
      if (anchor.sin < -0.5) startY = ly - lineHeight * (lines.length - 1) - 4;   // 위쪽 축: 위로 쌓기
      else if (anchor.sin > 0.5) startY = ly + 12;                                  // 아래쪽 축: 아래로 쌓기
      else startY = ly - (lineHeight * (lines.length - 1)) / 2 + 4;               // 옆쪽 축: 가운데 정렬
      lines.forEach(function (line, lineIndex) {
        var isValue = lineIndex === lines.length - 1;
        var text = make('text', {
          x: lx.toFixed(1),
          y: (startY + lineIndex * lineHeight).toFixed(1),
          'text-anchor': textAnchor,
          class: isValue ? 'radar-value' : 'radar-label'
        }, svg);
        text.textContent = line;
      });
    });

    container.setAttribute('role', 'img');
    container.setAttribute('aria-label', (options.title || '영역별 점수 레이더 차트') + ': ' + items.map(function (item) {
      return item.label + ' ' + item.value + '점';
    }).join(', '));
  }

  global.AXRadar = { render: render };
})(window);
