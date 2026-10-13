package bia.sentinela.home

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import bia.sentinela.SeniorPage
import bia.sentinela.SentinelaApi
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.launch

/** One senior's page: GET /seniors/{id} (seniors §3.3). */
@HiltViewModel
class SeniorViewModel @Inject constructor(private val api: SentinelaApi) : ViewModel() {
    var page by mutableStateOf<Load<SeniorPage>>(Load.Loading)
        private set

    /** [id] is null on the senior's own home: the one senior their grant names. */
    fun reread(id: String?) {
        viewModelScope.launch { page = page.after(read(id)) }
    }

    private suspend fun read(id: String?): Answer<SeniorPage> {
        val seniorId = id ?: when (val own = answer { api.seniors("senior") }) {
            is Answer.No -> return own
            is Answer.Ok -> own.value.firstOrNull()?.id ?: return Answer.No(Failure.NotFound)
        }
        return answer { api.senior(seniorId) }
    }
}
