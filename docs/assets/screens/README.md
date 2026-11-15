# 截图清单 / Screenshot slots

把截好的 PNG 用**同名文件**覆盖这里的占位图即可，页面会自动引用，不需要改 HTML。
文件名和尺寸必须完全一致；页面按这个尺寸预留了位置。

所有图片：PNG、sRGB、无透明背景、无圆角/阴影裁切、不要包含个人信息（真实姓名、邮箱、公司项目名、浏览器标签、文件路径）。用假项目名或空白文档。

## 总览

| 文件 | 尺寸 | 内容 | 页面位置 |
|---|---|---|---|
| `hero-desktop.png` | 2560 × 1440 | 整个桌面：dwindle 布局 + 状态栏 | 首页 hero |
| `scrolling-layout.png` | 2560 × 1440 | scrolling 布局：多列、标签列、右侧 peek | 首页 + 文档 scrolling |
| `floating-window.png` | 1600 × 1000 | 浮动窗口压在平铺窗口上 | 文档 floating |
| `bar.png` | 2560 × 120 | 只截状态栏（上下带一点桌面） | 文档 status bar |
| `launcher.png` | 1200 × 800 | Alt+Space 启动器打开、有搜索结果 | 文档 launcher |
| `system-menu.png` | 800 × 900 | Alt+M 系统菜单打开 | 文档 launcher/system menu |
| `settings.png` | 1400 × 900 | 设置编辑器，Status bar 或 Shortcuts 页 | 文档 settings |
| `resize-bracket.png` | 800 × 600 | Alt+右键拖拽时的红色角标特写 | 文档 floating |

## 拍摄前的统一设置

1. **分辨率与缩放**：显示器设为 2560 × 1440、100% 缩放最省事。如果是 4K，按 3840 × 2160 截，再用图片工具缩到 2560 × 1440（Lanczos），不要用 Windows 的“放大”或浏览器缩放。
2. **主题**：Astur 和所有示例应用都用深色主题。壁纸选深色、低对比、无文字，避免和窗口抢注意力。
3. **桌面**：隐藏桌面图标；关掉与画面无关的窗口；不要出现 Windows 任务栏（Astur 的 bar 就是状态栏；如果任务栏也在，画面会显得很乱）。
4. **内容**：用假项目名，例如 `nebula/`、`src/main.rs`、`docs/`。浏览器只开一个文档页，不要开邮箱、聊天、云盘。
5. **截屏方式**：`Win + Shift + S` 区域截图，或 `Win + PrtScn` 全屏后裁剪。不要用 `Alt + PrtScn`：Alt 是 Astur 的主键，容易和窗口管理操作冲突。
6. **精确裁剪**：用能输入精确宽高的工具（Photoshop、Affinity、IrfanView、ShareX 的固定区域模式）。页面按原始比例显示，尺寸不对会变形或出现空白。

## 每张图怎么摆

### 1. `hero-desktop.png` — 2560 × 1440

首页第一眼，信息量要够但不乱。

- 一个干净的 dwindle 工作区（默认布局），3–4 个窗口：
  - 左侧大窗口：VS Code 或 Neovim，打开一个假项目，行号/文件树可见；
  - 右上一个浏览器：Astur 文档或 GitHub 页面；
  - 右下两个终端：一个 `cargo build`，一个 `git status`，输出简短；
  - 或者再加一个文件管理器，但不要超过 5 个窗口。
- Astur 状态栏在顶部或底部都行，要完整可见：workspace pills、当前窗口标题、右侧 CPU/RAM/音量/时钟。
- 不要开浮动窗口，这张图负责讲“平铺 + 状态栏”。
- 壁纸暗一点，窗口间距（8 px gap）要能看出来。

### 2. `scrolling-layout.png` — 2560 × 1440

这张图是原网站缺的，重点展示 Niri 式横向列。

- 把当前显示器/工作区布局设为 `scrolling`（Settings → Layouts，或 `layout = scrolling` 后重载）。
- 打开 4–5 列，宽度不同：
  - 第 1 列：编辑器（约 0.5 宽）；
  - 第 2 列：浏览器（约 0.667 宽）；
  - 第 3 列：两个终端叠成一列，或做成 tabbed 列（`Alt+Shift+T`），标签栏可见；
  - 第 4 列：再一个窗口，只露出一点，形成右侧 peek。
- 让“当前列”在屏幕中间，左右都能看到相邻列的一部分；不要所有列都完整可见，否则像普通 columns 布局。
- 状态栏最好能看出当前是 scrolling（layout widget 显示 `scrolling`）。

### 3. `floating-window.png` — 1600 × 1000

- 背景：2–3 个平铺窗口，保持暗色。
- 前景：一个浮动窗口，例如计算器、设置对话框或一个小的 Markdown 预览；位置略偏右下，不要完全居中，让背后的平铺结构可见。
- 浮动窗口要有清晰的边框/阴影，和背后的窗口拉开层次；如果用了 `float_focused_border`，让颜色可见。
- 裁成 1600 × 1000，窗口边缘不要贴边，四周留 40–80 px 背景。

### 4. `bar.png` — 2560 × 120

- 只截状态栏区域，横向 2560 px，纵向 120 px；bar 本身大约在图片垂直中间，上下各留一点桌面背景。
- 必须完整包含三个区域：
  - 左：workspace pills（至少 4 个，含当前工作区高亮）+ 应用按钮；
  - 中：当前窗口标题；
  - 右：layout、CPU、RAM、音量、日期、时钟（至少 5 个 widget）。
- 不要裁掉左右边缘；不要有鼠标悬停高亮或 tooltip。
- 如果 bar 在屏幕顶部，直接从全屏图裁顶部 120 px；在底部就裁底部 120 px。

### 5. `launcher.png` — 1200 × 800

- 按 `Alt + Space` 打开启动器，输入 `ter` 或 `code`，让结果列表出现 4–6 项。
- 画面包含：搜索框、结果列表、每项图标、选中项高亮、底部键盘提示（如果有）。
- 背景是暗色桌面/窗口，启动器面板居中；不要出现真实文件名、最近打开的个人文档。
- 裁 1200 × 800，面板四周留出背景，不要贴边。
- 启动器打开后会接管键盘，`Win+Shift+S` / `PrtScn` 不会触发。用延迟截图：先在仓库根目录运行
  `powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File tools\capture_launcher.ps1 -Delay 10`，
  再按 `Alt+Space` 输入查询；10 秒后自动保存到桌面 `launcher.png`，最后裁成 1200 × 800。
  也可以用截图工具的 5 秒延迟模式。

### 6. `system-menu.png` — 800 × 900

- 按 `Alt + M` 打开系统菜单（默认键是 M；如果你改过 `key_system_menu`，用你自己的键）。
- 画面要能看到：
  - 电源区：Lock、Sleep、Restart、Shut down；
  - Astur 区：Settings、Open config、Reload、Restart Astur、Exit Astur；
  - 如果有 Screenshot / Wallpapers 也保留。
- 菜单本身大约 380 px 宽，800 × 900 的画面会带背景；让菜单居中偏上，背景暗且干净。
- 不要展开二级确认框。

### 7. `settings.png` — 1400 × 900

- 从托盘打开 Settings，把窗口拉到 1400 × 900 左右。
- 推荐页面：**Status bar**（能看到 shape、palette、三个 zone 的字段和 widget 颜色），或 **Shortcuts**（能看到 main_key 和各快捷键字段）。二选一，优先 Status bar，因为视觉上更能说明 Astur 的 bar。
- 左侧导航、页面标题、主要控件都要完整；不要出现滚动条压住内容。
- 如果窗口有标题栏，保留；不要截到桌面其他窗口。
- 设置里的路径如果是 `C:\Users\你的名字\...`，换成 `C:\Tools\Astur\` 之类的示例路径，或直接裁掉。

### 8. `resize-bracket.png` — 800 × 600

- 这是细节图，不是全屏图：按住 `Alt`，在窗口右下角（或任一角）按住右键拖动，出现红色角标时截图。
- 画面里要有：窗口角、红色 bracket、被拖动窗口的边缘，背景可以虚化/暗化。
- 实际操作时用左手按 `Win + PrtScn` 全屏截，再裁 800 × 600；或者用 ShareX 的延迟截图。
- 如果截不到，可以用 `floating-window.png` 的角部放大代替，但页面会按 800 × 600 显示，建议还是拍一张。

## 替换后检查

```powershell
# 在仓库根目录
python -m http.server -d docs 8123
```

打开 `http://localhost:8123/` 和 `http://localhost:8123/docs.html`，确认：

- 图片没有拉伸、没有黑边、没有占位文字；
- 首页 hero 在 1440 宽和手机宽度下都正常；
- `bar.png` 没有被压扁（它是 2560 × 120 的长条）；
- 文档里的图注仍然准确（如果截图内容和图注不一致，改图注或重拍）。

替换完删掉本文件也可以，留着方便下次更新截图。
