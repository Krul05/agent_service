# agent_service

Целью работы являлось создание воспроизводимого и расширяемого пайплайна, способного автоматически анализировать требования задачи, вносить изменения в код, выполнять проверки качества и принимать решение о завершении либо повторе цикла разработки без участия человека.

Решение реализовано в виде GithubApp и состоит из 3 питон-пакетов: code_agent, review_agent и app. Для обеспечения воспроизводимости и удобства запуска в репозитории присутствует Docker-конфигурация. Архитектура решения позволяет расширять функциональность, адаптировать стратегию ревью и интегрировать дополнительные проверки, что делает систему пригодной для дальнейшего развития и практического применения. 

Приложение тестировалось с помощью ngrok:


<img width="1453" height="456" alt="image" src="https://github.com/user-attachments/assets/22443b01-38c6-4d88-a91a-95b1a3c84023" />


При подключении приложения созданного мной приложения https://github.com/apps/my-agent-service, запускается review_agent+CI:


<img width="1273" height="672" alt="image" src="https://github.com/user-attachments/assets/61238f33-d8f1-43ad-b310-cf52aeab6d62" />

<img width="1383" height="428" alt="image" src="https://github.com/user-attachments/assets/664a4fc7-0e34-4183-bf3c-f0bb86c949e7" />


При создании нового Issue срабатывает триггер:


<img width="1129" height="605" alt="image" src="https://github.com/user-attachments/assets/c84b04ba-210d-4a6b-8202-6ccdef0907a9" />

<img width="986" height="166" alt="image" src="https://github.com/user-attachments/assets/24482d78-a483-4723-9ee5-e9d9c62065ac" />

Ссылка на тестовую дирректорию: https://github.com/Krul05/megaschool_test

Пример .env:

HOST=0.0.0.0

PORT=8080

GITHUB_APP_ID=2759740

GITHUB_APP_PRIVATE_KEY_PATH=/run/secrets/github_app_private_key.pem

GITHUB_WEBHOOK_SECRET=...

API_KEY=...

MODEL=gpt://b1g5ehq51foggd0ggqsq/yandexgpt-lite

LLM_BASE_URL=https://llm.api.cloud.yandex.net

BASE_BRANCH=master

MAX_ITERS=5

WORKDIR=/tmp/agent-workdir

