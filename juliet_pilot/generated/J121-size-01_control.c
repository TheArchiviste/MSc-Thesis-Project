#include "std_testcase.h"
void case_entry(void)
{
    int * data;
    data = NULL;
    data = (int *)ALLOCA(10*sizeof(int));
    {
        int source[10] = {0};
        memcpy(data, source, 10*sizeof(int));
        printIntLine(data[0]);
    }
}

int main(void)
{
    case_entry();
    return 0;
}
