package io.github.cheeringsoul.persistence.pojo;

import lombok.Getter;
import lombok.Setter;
import lombok.ToString;
import org.jdbi.v3.core.mapper.reflect.ColumnName;

@Getter
@Setter
@ToString
public class RelatedSymbolCount extends Base {
    private long id;
    @ColumnName("chat_id")
    private long chatId;
    @ColumnName("summary_id")
    private long summaryId;
    private String symbol;
    private int count;
}
