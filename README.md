# DataLab

VSM(M-H 루프)·XRD 결과를 해석하고 논문·PPT용 그래프를 그리는 Windows 프로그램. 개발자 KIM YEONGDO.

## 쓰는 법
1. `DataLab.exe` 실행 → 파일을 창에 끌어다 놓거나 **파일 › 열기**(폴더도 됨).
2. 왼쪽 위에서 **VSM / XRD**를 고르고, 목록에서 체크한 시료만 겹쳐 그린다.
3. 오른쪽에서 스타일(PPT용·논문 1단 8.5 cm·논문 2단 17.5 cm), 원점 확대 인셋, H 단위(Oe·kA/m), 자장 오프셋 보정, XRD 세로 띄우기를 바꾼다.
4. **파일 › 그림 저장**: PNG·TIF 600 dpi, SVG·PDF 벡터. **Ctrl+Shift+C**: 그림을 클립보드로(PPT에 바로 붙여넣기).
5. **결과 표 복사**: Excel에 붙여넣기.

## 읽는 파일
- VSM: Lake Shore 8600 csv(장비 계산값과 다시 계산한 값을 대조), 옛 IDEAS VSM txt, 숫자 2열 텍스트(첫 열 H, 둘째 열 M)
- XRD: .xrdml, .rasx, X'Pert csv, 2열 텍스트 — 판정·피크·결정립 크기는 [xrdcheck](https://github.com/Dubitnarae/xrd-amorph-checker) 결과를 그대로 보여 준다.

## VSM 계산
- Hc: M이 0을 지나는 자장들의 절댓값 평균(장비와 같은 식). 루프가 치우치면 반폭과 치우침(H 바이어스)을 함께 표시
- Mr: H가 0을 지날 때 M들의 절댓값 평균, Ms: (M 최대 − 최소)/2, 각형비 Mr/Ms
- 자장 오프셋 보정: 입력한 값만큼 H를 옮겨 계산하고 보정 전 Hc도 함께 표시
