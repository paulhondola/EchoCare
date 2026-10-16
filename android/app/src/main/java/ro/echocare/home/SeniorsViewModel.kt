package ro.echocare.home

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
import ro.echocare.SeniorRow

/** The seniors the caller reaches in the role of the route: GET /seniors?role= (seniors SE6). */
@HiltViewModel
class SeniorsViewModel @Inject constructor(private val api: EchoCareApi, saved: SavedStateHandle) :
    ViewModel() {
    private val role = saved.toRoute<SeniorsRoute>().role

    var seniors by mutableStateOf<Load<List<SeniorRow>>>(Load.Loading)
        private set

    /** Called when the screen appears and on every timed re-read (06 §3). */
    fun reread() {
        viewModelScope.launch { seniors = seniors.after(answer { api.seniors(role) }) }
    }
}
