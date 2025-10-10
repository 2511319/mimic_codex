# План тестирования Vertical Slice

1. Авторизация через initData → JWT: проверка TTL, повторной выдачи с тем же initData и структуры токена.
2. Управление кампанией: сценарий Retcon/Override с аудитом и семантической валидацией переходов.
3. Генерация сцены: валидация JSON-схем SceneResponse и SocialResponse, сравнение с golden-скриптами.
4. Медиапайплайн: создание задания TTS, ожидание события `rpg.media.job.done.v1`, проверка retry-policy DLQ.
