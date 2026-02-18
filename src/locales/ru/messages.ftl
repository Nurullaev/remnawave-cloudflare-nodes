# Жизненный цикл сервиса
service-started = <b>🚀 Сервис запущен</b>
    Мониторинг активен.

    { $summary }

service-stopped = <b>🛑 Сервис остановлен</b>
    Мониторинг выключен.

# Изменения статуса нод
node-became-healthy = <b>✅ Нода онлайн</b>
    { $name } ({ $address }) доступна.

    📊 Ноды: { $online }/{ $total } онлайн, { $disabled } отключено

node-became-unhealthy = <b>❌ Нода офлайн</b>
    { $name } ({ $address }) недоступна.
    Причина: { $reason }

    📊 Ноды: { $online }/{ $total } онлайн, { $disabled } отключено

# Операции DNS
dns-record-added = <b>📝 DNS обновлен</b>
    Добавлен { $ip } → { $domain }

dns-record-removed = <b>🗑️ DNS удален</b>
    Удален { $ip } из { $domain }

# Ошибки
dns-operation-error = <b>⚠️ Ошибка DNS</b>
    Не удалось { $action } { $ip } для { $domain }
    Ошибка: { $error }

health-check-error = <b>⚠️ Ошибка проверки</b>
    Ошибка при проверке: { $error }

# Критические состояния
all-nodes-down = <b>🔴 КРИТИЧНО: Все ноды недоступны</b>
    Все { $total } нод недоступны.
    Затронуты: { $nodes }

    DNS записи очищены. Требуется немедленное вмешательство.

all-nodes-recovered = <b>🟢 Восстановление: Ноды снова онлайн</b>
    { $online } из { $total } нод снова доступны.
    DNS записи восстановлены.

# События API
api-config-updated = <b>⚙️ Конфигурация обновлена через API</b>
    { $changes }
    От: { $ip }

api-domain-added = <b>➕ Домен добавлен через API</b>
    { $domain } ({ $zones } зон(а))
    От: { $ip }

api-domain-removed = <b>➖ Домен удален через API</b>
    { $domain }
    От: { $ip }

api-zone-added = <b>➕ Зона добавлена через API</b>
    { $zone }.{ $domain } ({ $ips } IP)
    От: { $ip }

api-zone-updated = <b>⚙️ Зона обновлена через API</b>
    { $zone }.{ $domain }
    { $changes }
    От: { $ip }

api-zone-removed = <b>➖ Зона удалена через API</b>
    { $zone }.{ $domain }
    От: { $ip }
