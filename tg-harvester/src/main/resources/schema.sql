CREATE TABLE chat_messages
(
    id           BIGINT GENERATED ALWAYS AS IDENTITY NOT NULL,
    message_id   BIGINT,
    chat_id      BIGINT      NOT NULL,
    group_name   TEXT        NOT NULL,
    sender_id    BIGINT      NOT NULL,
    message_text TEXT,
    urls         TEXT[],
    timestamp    TIMESTAMPTZ NOT NULL,
    CONSTRAINT chat_messages_pk PRIMARY KEY (id)
);


CREATE TABLE channel_news
(
    id           BIGINT GENERATED ALWAYS AS IDENTITY NOT NULL,
    message_id   BIGINT,
    chat_id      BIGINT      NOT NULL,
    group_name   TEXT        NOT NULL,
    message_text TEXT,
    urls         TEXT[],
    timestamp    TIMESTAMPTZ NOT NULL,
    CONSTRAINT channel_news_pk PRIMARY KEY (id)
);

CREATE TABLE link_content
(
    id                     BIGINT GENERATED ALWAYS AS IDENTITY NOT NULL,
    related_super_group_id BIGINT,
    url                    TEXT,
    title                  TEXT,
    content                TEXT,
    timestamp              TIMESTAMPTZ NOT NULL,
    CONSTRAINT link_content_pk PRIMARY KEY (id)
);

CREATE TABLE config
(
    id        int GENERATED ALWAYS AS IDENTITY NOT NULL,
    "version" varchar                          NOT NULL,
    config    json                             NOT NULL,
    CONSTRAINT config_pk PRIMARY KEY (id),
    CONSTRAINT config_unique UNIQUE ("version")
);