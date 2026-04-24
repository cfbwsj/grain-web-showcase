# GRAIN Web Retrieval Showcase

这是一个为 GRAIN / CLIP4ReID 项目准备的轻量 Web 展示系统。它是独立的 FastAPI + 静态单页应用，支持部署到 Render，也预留了后续接入 GRAIN checkpoint、CLIP 语义检索和视频检索的接口。

## 已实现功能

- 登录、注册、邀请码注册和超级管理员账号。
- 批量上传图片集，支持目录上传，并从上级目录或文件名推断 `person_key`。
- 新图片入库后自动建立检索向量。
- 文本检索图片，中文查询会在后端做轻量英文归一化。
- 属性表单检索，后端将属性组合成英文描述后检索。
- 以图搜图，支持返回命中行人的全部照片。
- 检索耗时、相似度百分比和排序条可视化。
- 图库页面展示当前支持检索的图片数据。
- 检索历史记录。
- 视频上传和视频检索预留 API。

## 项目结构

```text
grain_web_showcase/
  app/                FastAPI 后端
  web/                静态前端
  data/               本地运行时数据，已被 .gitignore 忽略
  render.yaml         Render Blueprint
  requirements.txt    默认轻量依赖
  requirements-clip.txt
```

## 本地运行

```bash
cd grain_web_showcase
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

默认超级管理员：

```text
email: admin@grain.local
password: ChangeMe-Grain-Admin-2026!
```

生产环境必须通过环境变量修改 `SUPER_ADMIN_PASSWORD` 和 `SECRET_KEY`。

## Render 部署

推荐使用本仓库的 `render.yaml` 创建 Web Service。关键配置：

```text
Build Command: pip install -r requirements.txt
Start Command: uvicorn app.main:app --host 0.0.0.0 --port $PORT
DATA_DIR: /var/data
```

如果需要上传图片在重启后仍然保留，请为服务挂载 persistent disk 到 `/var/data`。如果不挂载磁盘，SQLite 数据库和上传文件会随着实例重建而丢失。

建议设置这些环境变量：

```text
SECRET_KEY=<Render generate value or long random string>
SUPER_ADMIN_EMAIL=<your-admin-email>
SUPER_ADMIN_PASSWORD=<strong-password>
INVITE_BOOTSTRAP_CODES=<optional-initial-invite-code>
COOKIE_SECURE=true
RETRIEVER_BACKEND=feature
```

## 检索后端

默认 `RETRIEVER_BACKEND=feature`，只依赖 Pillow/Numpy。它适合展示、快速部署和资源有限的实例，主要利用颜色直方图、文件名、标签和行人 ID 进行检索。

如果 Render 实例内存足够，可以安装可选依赖并开启 CLIP：

```text
Build Command: pip install -r requirements.txt -r requirements-clip.txt
RETRIEVER_BACKEND=clip
CLIP_MODEL_NAME=openai/clip-vit-base-patch32
```

切换后端后，在管理员页面点击“重建图片索引”。

## 接入 GRAIN checkpoint

当前目录没有可部署的 GRAIN checkpoint，所以系统先以内置检索后端上线。后续可在 `app/retrievers.py` 新增 `GrainRetriever`：

1. 读取原项目的 config 和 checkpoint。
2. 调用 `build_model(args)` 并加载权重。
3. 对上传图片执行同训练一致的 transforms。
4. 对文本执行 GRAIN tokenizer。
5. 在 `encode_image` / `encode_text` 返回归一化向量。

这样前端和数据库层不需要改动，只需要新增后端并设置 `RETRIEVER_BACKEND=grain`。

## API 摘要

- `POST /api/auth/login`
- `POST /api/auth/register`
- `GET /api/auth/me`
- `POST /api/images/upload`
- `GET /api/images`
- `POST /api/search/text`
- `POST /api/search/attributes`
- `POST /api/search/image`
- `POST /api/search/image-id`
- `GET /api/search/history`
- `POST /api/admin/invites`
- `POST /api/admin/reindex`
- `POST /api/videos/upload`
- `POST /api/search/video`

