class SavePolicy:
    MAX_SAVED_ITINERARIES = 50

    def can_save(self, current_count: int) -> bool:
        return current_count < self.MAX_SAVED_ITINERARIES
