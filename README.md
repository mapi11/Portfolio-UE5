# Technical Art Portfolio - Unreal Engine 5

Pet-проекты Technical Artist на Unreal Engine 5: VFX на Niagara, материалы и шейдеры, оптимизация.

**Максим Астраханцев** - Telegram [@mapiAP](https://t.me/mapiAP)

Портфолио на Unity: [Portfolio-Unity](https://github.com/mapi11/Portfolio-Unity)

## Проекты

### Smoke: стенд дыма

![Smoke](Docs/Images/smoke_stand.png)

Первый стенд для VFX: симметричная комната в стиле The Finals со скруглёнными стенами, глянцевым полом и синей нишей, в центре подиум с разметкой - кольца 0.5, 1 и 1.5 м и линейка с засечками каждые 10 см, по ним сразу видно масштаб эффекта. По комнате можно ходить персонажем из шаблона Third Person.

Дым на Niagara без текстур: клуб рисуется в материале (круглая маска и fbm-шум в Custom-ноде), у каждой частицы свой узор, шум плывёт вверх, Depth Fade смягчает край у поверхностей. В системе Curl Noise, Drag, рост и вращение частиц, плавное появление и затухание.

Комната собирается одним Python-скриптом `Tools/StyleKit/build_smoke_room.py`, повторный запуск пересобирает её с нуля:
- меши генерируются процедурно (`meshgen.py`), без Nanite, коллизия по самому мешу;
- материалы - HLSL Custom-ноды в мировых координатах без текстур и UV: разводы на глянце, разметка подиума;
- свет - rect light и эмиссивные панели; панели исключены из сцены Lumen, иначе его грубый кэш давал квадратные блики на глянцевом полу.

Сцена: `PortfolioUE5/Content/Maps/Smoke.umap`

## Как открыть

Unreal Engine 5.8.4. Открыть `PortfolioUE5/PortfolioUE5.uproject`. Ассеты хранятся в Git LFS: перед клонированием нужен `git lfs install`.
