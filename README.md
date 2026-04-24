# GRAIN Web Retrieval Showcase

这是一个为 GRAIN / CLIP4ReID 项目准备的轻量 Web 展示系统。它是独立的 FastAPI + 静态单页应用，支持部署到 Render，也预留了后续接入 GRAIN checkpoint、CLIP 语义检索和视频检索的接口。

## 已实现功能

- 登录、注册、邀请码注册和超级管理员账号。
- 批量上传图片集，支持目录上传，并从上级目录或文件名推断 `person_key`。
- 文本检索图片，中文查询会在后端做轻量英文归一化。
- 属性表单检索，后端将属性组合成英文描述后检索。
- 以图搜图，支持返回命中行人的全部照片。
- 检索耗时、相似度百分比和排序条可视化。
- 图库页面展示当前支持检索的图片数据。
- 检索历史记录。
- 视频上传和视频检索预留 API。
- 普通用户仅能看到和检索自己的上传；管理员可查看全部图库。
- 图库支持删除图片；普通用户只能删除自己的图片。
- 双分支检索：`person` 分支优先走 GRAIN，`general` 分支优先走 OpenCLIP。
- 上传阶段不再强制计算 embedding，首次检索或重建索引时再懒加载缓存。

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

如果你使用的是 Render 免费实例，它不能挂载 persistent disk，且 `/var/data` 往往不可写。当前版本会在这种情况下自动回退到项目内的本地可写目录继续启动，但这些数据仍然是非持久化的，只适合临时演示。

建议设置这些环境变量：

```text
SECRET_KEY=<Render generate value or long random string>
SUPER_ADMIN_EMAIL=<your-admin-email>
SUPER_ADMIN_PASSWORD=<strong-password>
INVITE_BOOTSTRAP_CODES=<optional-initial-invite-code>
COOKIE_SECURE=true
RETRIEVER_BACKEND=feature
```

免费实例建议直接不要手动设置 `DATA_DIR`，或者即使设置成 `/var/data`，应用也会自动回退到本地目录。

## 检索后端

当前版本使用双分支后端：

- `PERSON_RETRIEVER_BACKEND=grain`
- `GENERAL_RETRIEVER_BACKEND=openclip`

```text
Build Command: pip install -r requirements.txt -r requirements-clip.txt
PERSON_RETRIEVER_BACKEND=grain
GENERAL_RETRIEVER_BACKEND=openclip
GENERAL_OPENCLIP_MODEL=ViT-B-16
GENERAL_OPENCLIP_PRETRAINED=laion2b_s34b_b88k
GRAIN_CONFIG_FILE=/absolute/path/to/configs.yaml
GRAIN_CHECKPOINT=/absolute/path/to/best_map.pth
```

如果 `GRAIN_CONFIG_FILE` 或 `GRAIN_CHECKPOINT` 未提供，系统会按 `ALLOW_RETRIEVER_FALLBACK=true` 自动回退到轻量特征检索，不会阻塞服务启动。

## GRAIN 权重说明

当前仓库里没有现成的 `.pth` checkpoint 文件，所以 Render 部署时需要你自己提供：

1. `configs.yaml`
2. 对应的 `best_map.pth` 或其它推理 checkpoint

如果暂时没有提供，系统会自动回退，不影响页面上线。

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
