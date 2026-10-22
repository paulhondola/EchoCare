package ro.echocare.das

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import java.time.Instant
import javax.inject.Inject
import kotlinx.coroutines.launch
import ro.echocare.EchoCareApi
import ro.echocare.IncidentRow
import ro.echocare.home.Load
import ro.echocare.home.after
import ro.echocare.home.answer

/** The DAS home: GET /incidents?status=open,in_progress (04 §1, UC-12). */
@HiltViewModel
class IncidentsViewModel @Inject constructor(private val api: EchoCareApi) : ViewModel() {
    var incidents by mutableStateOf<Load<List<IncidentRow>>>(Load.Loading)
        private set

    /**
     * The time "acum …" is counted to. Unchanged data is an equal state that redraws nothing, so
     * the time is its own state, set on every re-read.
     */
    var now by mutableStateOf(Instant.now())
        private set

    /** Called when the screen appears and on every timed re-read (06 §3). */
    fun reread() {
        now = Instant.now()
        viewModelScope.launch { incidents = incidents.after(answer { api.incidents(ACTIVE) }) }
    }
}
