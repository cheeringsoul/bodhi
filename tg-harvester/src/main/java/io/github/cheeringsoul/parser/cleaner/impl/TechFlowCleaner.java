package io.github.cheeringsoul.parser.cleaner.impl;

import io.github.cheeringsoul.parser.cleaner.Cleaner;
import io.github.cheeringsoul.parser.cleaner.CleanerMeta;
import io.github.cheeringsoul.pojo.ChannelNewsEntity;
import io.github.cheeringsoul.pojo.LinkContent;
import lombok.extern.slf4j.Slf4j;

import java.util.Optional;

@Slf4j
@CleanerMeta(chatId = -1001735732363L)
public class TechFlowCleaner implements Cleaner<ChannelNewsEntity> {

    @Override
    public Optional<ChannelNewsEntity> clean(ChannelNewsEntity entity) {
        for (LinkContent item : entity.linkContents()) {
            if (item.crawledData().doc() == null) {
                continue;
            }
            String text = item.crawledData().doc().select(".art_detail_content").text().trim();
            if (text.isEmpty()) {
                log.warn("[Ignore message] TechFlow content is empty url {}", item.url());
                continue;
            }
            item.content(text);
        }
        return Optional.of(entity);
    }
}
