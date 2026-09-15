# Remote VM Operations Guide — Label Guardian

> Cập nhật: 2026-08-27
> Tên file được giữ để không làm hỏng link cũ; đây là runbook vận hành backend VM, không phải hướng dẫn phát triển trực tiếp trên production.

Production hiện dùng repo deploy `8uandj/Label_guardian`: Vercel host frontend; GCP VM host FastAPI, Agent runtime, Caddy và GitHub self-hosted runner. Kiến trúc/deploy chuẩn nằm trong [`HYBRID_VERCEL_VM_DEPLOYMENT.md`](HYBRID_VERCEL_VM_DEPLOYMENT.md).

## 1. Server contract

Thông tin hiện tại cần được xác minh lại trong GCP Console trước thao tác có ảnh hưởng:

```text
GCP project: ai-lab-16-gcp-505508
VM name: label-guardian-vm
Zone: asia-southeast1-a
API domain: https://api.labelguardian.space
Runtime source: /opt/label-guardian/app
Production env: /opt/label-guardian/.env.production
Compose file: docker-compose.selfhost.yml
```

Services trên VM:

```text
backend          FastAPI + Agent runtime
backend-migrate  one-shot Alembic migration profile
proxy            Caddy HTTPS reverse proxy
```

Frontend không chạy trên VM; Vercel phục vụ `labelguardian.space` và `www.labelguardian.space`.

## 2. Nguyên tắc

- Git `main` của deploy repository là source of truth.
- Không phát triển hoặc giữ hotfix chỉ tồn tại trên VM.
- Không copy `.env.production`, GCS credential, database dump hoặc token vào Git/workspace cá nhân.
- Không chạy migration thủ công nếu deploy workflow đang chạy.
- Không restart/delete container khi chưa chụp status/log và xác định phạm vi sự cố.
- Dùng GitHub Actions self-hosted runner cho deploy thường lệ; terminal VM chủ yếu để quan sát và phục hồi.

## 3. SSH

Ví dụ SSH config local:

```sshconfig
Host label-guardian-vm
  HostName 34.143.247.68
  User <VM_USER>
  IdentityFile ~/.ssh/<PRIVATE_KEY>
  IdentitiesOnly yes
  ServerAliveInterval 30
```

Kết nối:

```bash
ssh label-guardian-vm
```

IP/user/key có thể thay đổi; ưu tiên giá trị từ GCP Console hoặc access policy của team.

## 4. Kiểm tra read-only đầu tiên

```bash
cd /opt/label-guardian/app
git remote -v
git branch --show-current
git status --short
sudo docker compose --env-file /opt/label-guardian/.env.production \
  -f docker-compose.selfhost.yml --profile internet ps
```

Health bên ngoài:

```bash
curl -f https://api.labelguardian.space/health
curl -f https://api.labelguardian.space/ready
curl -f https://api.labelguardian.space/api/v1/health
```

`/health` chỉ chứng minh process sống; `/ready` còn kiểm tra PostgreSQL.

## 5. Logs

```bash
cd /opt/label-guardian/app
export SELFHOST_ENV_FILE=/opt/label-guardian/.env.production

sudo -E docker compose --env-file "$SELFHOST_ENV_FILE" \
  -f docker-compose.selfhost.yml logs --tail 200 backend

sudo -E docker compose --env-file "$SELFHOST_ENV_FILE" \
  -f docker-compose.selfhost.yml --profile internet logs --tail 200 proxy
```

Theo dõi realtime chỉ trong thời gian cần thiết:

```bash
sudo -E docker compose --env-file "$SELFHOST_ENV_FILE" \
  -f docker-compose.selfhost.yml logs -f --tail 100 backend
```

Không paste log chứa token, signed URL, database hostname/password hoặc user PII vào issue công khai.

## 6. Deploy chuẩn

Luồng chuẩn:

```text
feature/fix -> review/test -> push/merge main deploy repo
  -> Vercel deploy frontend
  -> .github/workflows/deploy-selfhost.yml deploy backend trên VM
```

Workflow backend:

1. Xác minh env/runtime directory.
2. Build candidate image.
3. Chạy migration one-shot.
4. Deploy candidate.
5. Kiểm tra `/health`, `/ready`, `/api/v1/health`.
6. Promote hoặc rollback stable backend image.

Theo dõi trong GitHub Actions. Chỉ dùng manual deployment khi workflow không thể chạy và incident owner cho phép; xem [`SELF_HOSTED_DEPLOYMENT.md`](SELF_HOSTED_DEPLOYMENT.md).

## 7. Production environment

File:

```text
/opt/label-guardian/.env.production
```

Trước thay đổi được phê duyệt:

```bash
sudo cp /opt/label-guardian/.env.production \
  /opt/label-guardian/.env.production.bak-$(date +%Y%m%d%H%M%S)
```

Các nhóm cấu hình nhạy cảm:

- Supabase JWT/PostgreSQL.
- GCS project/bucket/ADC hoặc service-account credential.
- OpenAI key.
- CORS và public API domain.

Biến `VITE_*` là build-time frontend configuration và phải đổi/redeploy trên Vercel, không phải bằng restart backend VM.

Sau thay đổi env backend, validate Compose trước khi restart:

```bash
sudo -E docker compose --env-file /opt/label-guardian/.env.production \
  -f docker-compose.selfhost.yml --profile internet config --quiet
```

## 8. Incident checklist

### Backend unhealthy

1. Kiểm tra Compose status và backend logs.
2. Kiểm tra migration head/database connectivity.
3. Kiểm tra production env có placeholder/localhost không.
4. Kiểm tra GCS credential/cache/model file nếu lỗi ở dataset/Agent.
5. Dùng stable image rollback flow; không tự downgrade database.

### API HTTPS lỗi

1. Xác minh DNS `api.labelguardian.space` trỏ đúng VM.
2. Kiểm tra firewall TCP 80/443.
3. Kiểm tra proxy container và Caddy logs.
4. Kiểm tra ACME state/clock/network.

### Frontend lỗi nhưng API healthy

1. Kiểm tra Vercel deployment và build logs.
2. Kiểm tra `VITE_API_BASE_URL`, Supabase public variables và CSP.
3. Kiểm tra Supabase Site URL/Redirect URLs.
4. Không restart VM nếu lỗi chỉ thuộc frontend bundle.

### App không tải dữ liệu

1. `/ready` phải trả 200.
2. Browser request phải có bearer token hợp lệ.
3. Kiểm tra role/disabled trong `application_users` qua backend/admin flow.
4. Kiểm tra GCS permission, object key và dataset identity/split.

## 9. Stop/start VM

Container dùng `restart: unless-stopped`; Docker phải được enable để tự khởi động sau VM reboot:

```bash
sudo systemctl enable --now docker
sudo systemctl is-enabled docker
```

Nếu dừng VM để tiết kiệm chi phí, dùng GCP command/console; không `docker compose stop` trước vì container bị stop explicit có thể không tự lên lại:

```bash
gcloud compute instances stop label-guardian-vm --zone asia-southeast1-a
gcloud compute instances start label-guardian-vm --zone asia-southeast1-a
```

Sau khi start, chạy health checks và xác minh container status.

## 10. Kết thúc phiên vận hành

- Ghi lại incident/change và thời điểm.
- Không để source tree trên VM dirty; hotfix phải được đưa về branch và deploy lại qua Git.
- Xóa file tạm có secret theo policy của team.
- Xác nhận backend/proxy healthy và API checks trả 200.
- Nếu đổi auth/domain, xác nhận Supabase redirect/CORS và Vercel environment đồng bộ.
- Nếu đổi database, ghi migration revision và backup/restore evidence.
