package com.voss.web.api;

import com.voss.web.db.PalletPlacementRepository;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

/** 실시간 상태 토픽이 없는 경우에도 가장 최근 DB 적재 회차를 화면에 표시한다. */
@RestController
public class PalletPlacementController {
    private final PalletPlacementRepository placements;
    public PalletPlacementController(PalletPlacementRepository placements) {
        this.placements = placements;
    }

    @GetMapping("/api/pallet/placements/latest")
    public Map<String, Object> latest() { return placements.latest(); }
}
