package ro.echocare.das

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.navigation.toRoute
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.launch
import ro.echocare.EchoCareApi
import ro.echocare.IncidentPage
import ro.echocare.home.IncidentRoute
import ro.echocare.home.Load
import ro.echocare.home.after
import ro.echocare.home.answer

/** One incident: GET /incidents/{id} (04 §1, UC-11). */
@HiltViewModel
class IncidentViewModel @Inject constructor(private val api: EchoCareApi, saved: SavedStateHandle) :
    ViewModel() {
    val id = saved.toRoute<IncidentRoute>().id

    var page by mutableStateOf<Load<IncidentPage>>(Load.Loading)
        private set

    /** Called when the screen appears and on every timed re-read (06 §3). */
    fun reread() {
        viewModelScope.launch { page = page.after(answer { api.incident(id) }) }
    }
}
