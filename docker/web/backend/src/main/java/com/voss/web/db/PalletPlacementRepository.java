package com.voss.web.db;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Repository;

/** 가장 최근 팔레트 회차에 기록된 실제 적재 결과를 읽는다. */
@Repository
public class PalletPlacementRepository {
    private final DbAccess db;

    public PalletPlacementRepository(DbAccess db) { this.db = db; }

    public Map<String, Object> latest() {
        String sql = "SELECT run_id, box_id, dong, route_index, pallet_slot, result "
                + "FROM pallet_log WHERE run_id = ("
                + "SELECT run_id FROM pallet_log "
                + "ORDER BY finished_at DESC NULLS LAST, inserted_at DESC LIMIT 1) "
                + "ORDER BY finished_at ASC NULLS LAST, inserted_at ASC, box_id ASC";
        List<Map<String, Object>> items = new ArrayList<>();
        String runId = "";
        try (Connection connection = db.openRead();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            try (ResultSet rows = statement.executeQuery()) {
                while (rows.next()) {
                    runId = rows.getString("run_id");
                    Map<String, Object> item = new LinkedHashMap<>();
                    item.put("box_id", rows.getString("box_id"));
                    item.put("dong", rows.getString("dong"));
                    item.put("route_index", rows.getObject("route_index"));
                    item.put("pallet_slot", rows.getObject("pallet_slot"));
                    item.put("result", rows.getString("result"));
                    items.add(item);
                }
            }
        } catch (SQLException exception) {
            throw db.dbError("팔레트 적재 기록 조회에 실패했습니다.");
        }
        return Map.of("run_id", runId, "items", items);
    }
}
