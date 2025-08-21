package io.github.cheeringsoul.persistence.dao;

import io.github.cheeringsoul.persistence.pojo.RelatedSymbolCount;
import org.jdbi.v3.sqlobject.config.RegisterBeanMapper;
import org.jdbi.v3.sqlobject.customizer.Bind;
import org.jdbi.v3.sqlobject.statement.SqlQuery;
import org.jdbi.v3.sqlobject.statement.SqlUpdate;

import java.util.List;

public interface RelatedSymbolDao {
    @SqlUpdate("""
        INSERT INTO related_symbol_count (summary_id, symbol, count)
        VALUES (:summaryId, :symbol, :count)
    """)
    void insert(@Bind("summaryId") long summaryId,
                @Bind("symbol") String symbol,
                @Bind("count") int count);

    @SqlQuery("SELECT symbol, count FROM related_symbol_count WHERE summary_id = :summaryId")
    @RegisterBeanMapper(RelatedSymbolCount.class)
    List<RelatedSymbolCount> findBySummaryId(@Bind("summaryId") long summaryId);
}
