package io.github.cheeringsoul.persistence.dao;

import io.github.cheeringsoul.persistence.pojo.RelatedSymbolCount;
import org.jdbi.v3.sqlobject.config.RegisterBeanMapper;
import org.jdbi.v3.sqlobject.customizer.BindBean;
import org.jdbi.v3.sqlobject.statement.SqlUpdate;

@RegisterBeanMapper(RelatedSymbolCount.class)
public interface RelatedSymbolCountDao {
    @SqlUpdate("""
            INSERT INTO related_symbol_count (chat_id, summary_id, symbol, count)
            VALUES (:chatId, :summaryId, :symbol, :count)
            """)
    long insert(@BindBean RelatedSymbolCount entity);
}
